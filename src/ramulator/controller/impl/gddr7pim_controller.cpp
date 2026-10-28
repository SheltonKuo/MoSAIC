#include <cassert>
#include <fmt/format.h>
#include <optional>
#include <stdexcept>

#include "ramulator/base/base.h"
#include "ramulator/controller/impl/hbm_controller_base.h"
#include "ramulator/controller/impl/lpddr5pim_types.h"
#include "ramulator/controller/refresh/i_refresh_manager.h"
#include "ramulator/controller/rowpolicy/i_row_policy.h"
#include "ramulator/controller/scheduler/i_scheduler.h"
#include "ramulator/dram/dram_spec.h"

namespace Ramulator {

class GDDR7PIMController final : public HBMControllerBase {
  RAMULATOR_REGISTER_IMPLEMENTATION_DERIVED(
      IController, GDDR7PIMController, HBMControllerBase, "GDDR7PIM")

 public:
  void init() override {
    HBMControllerBase::init();

    RAMULATOR_PARSE_PARAM(m_rck_mode_str, std::string, "rck_mode").default_val("always_on");
    RAMULATOR_PARSE_PARAM(m_rck_idle_threshold, int, "rck_idle_threshold").default_val(32);

    if      (m_rck_mode_str == "always_on")          m_rck_mode = RCKMode::AlwaysOn;
    else if (m_rck_mode_str == "start_with_read")     m_rck_mode = RCKMode::StartWithRead;
    else if (m_rck_mode_str == "start_with_rckstrt")  m_rck_mode = RCKMode::StartWithRCKStrt;
    else throw std::runtime_error(
        "GDDR7PIM: unsupported rck_mode '" + m_rck_mode_str + "'");

    const auto& spec = *m_device.m_spec;

    m_cmd_rckstrt   = spec.get_command_id("RCKSTRT");
    m_cmd_rckstop   = spec.get_command_id("RCKSTOP");
    m_cmd_rd        = spec.get_command_id("RD");
    m_cmd_rda       = spec.get_command_id("RDA");
    m_channel_level = spec.get_level_id("Channel");

    m_rck_state = (m_rck_mode == RCKMode::AlwaysOn) ? RCKState::Toggling : RCKState::Stopped;

    m_cmd_actab    = spec.get_command_id("ACTAB");
    m_cmd_macab    = spec.get_command_id("MACAB");
    m_cmd_macsb    = spec.get_command_id("MACSB");
    m_cmd_wr_bb     = spec.get_command_id("WR_BB");
    m_cmd_rd_bb    = spec.get_command_id("RD_BB");
    m_cmd_wr_rb    = spec.get_command_id("WR_RB");
    m_cmd_rd_rb    = spec.get_command_id("RD_RB");
    m_cmd_mv_rb     = spec.get_command_id("MV_RB");
    m_cmd_mv_bb     = spec.get_command_id("MV_BB");
    m_cmd_sfm      = spec.get_command_id("SFM");
    m_cmd_act_func = spec.get_command_id("ACT_FUNC");
    m_cmd_setm     = spec.get_command_id("SETM");
    m_cmd_seth     = spec.get_command_id("SETH");
    m_cmd_barrier  = spec.get_command_id("BARRIER");

    m_pim_final_cmds.resize(PIMRequestType::COUNT, -1);
    m_pim_final_cmds[PIMRequestType::MAC_AB]    = m_cmd_macab;
    m_pim_final_cmds[PIMRequestType::MAC_SB]    = m_cmd_macsb;
    m_pim_final_cmds[PIMRequestType::WR_BB]     = m_cmd_wr_bb;
    m_pim_final_cmds[PIMRequestType::MV_RB]     = m_cmd_mv_rb;
    m_pim_final_cmds[PIMRequestType::MV_BB]     = m_cmd_mv_bb;
    m_pim_final_cmds[PIMRequestType::RD_BB]     = m_cmd_rd_bb;
    m_pim_final_cmds[PIMRequestType::WR_RB]     = m_cmd_wr_rb;
    m_pim_final_cmds[PIMRequestType::RD_RB]     = m_cmd_rd_rb;
    m_pim_final_cmds[PIMRequestType::SFM]       = m_cmd_sfm;
    m_pim_final_cmds[PIMRequestType::ACT_FUNC]  = m_cmd_act_func;
    m_pim_final_cmds[PIMRequestType::SET_MODEL] = m_cmd_setm;
    m_pim_final_cmds[PIMRequestType::SET_HEAD]  = m_cmd_seth;
    m_pim_final_cmds[PIMRequestType::BARRIER]   = m_cmd_barrier;

    m_pim_buffer.max_size = 64;
  }

  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    HBMControllerBase::setup(frontend, memory_system);
    m_stats.add("pim_queue_len",    s_pim_queue_len);
    m_stats.add("num_rckstrt_issued", s_num_rckstrt_issued);
    m_stats.add("num_rckstop_issued", s_num_rckstop_issued);
  }

  bool send(Request& req) override {
    if (req.type_id == Request::Type::Read || req.type_id == Request::Type::Write) {
      return ControllerBase::send(req);
    }

    if (req.type_id < 0 || req.type_id >= PIMRequestType::COUNT ||
        m_pim_final_cmds[req.type_id] < 0) {
      throw std::runtime_error(fmt::format(
          "GDDR7PIMController: unknown or unsupported PIM request type_id {}", req.type_id));
    }

    m_addr_mapper->apply(req);
    req.addr_vec[0] = m_channel_id;
    req.final_command = m_pim_final_cmds[req.type_id];
    req.arrive = m_clk;

    bool ok = m_pim_buffer.enqueue(req);
    if (!ok) req.arrive = -1;
    return ok;
  }

  void tick() override {
    hbm_tick_prologue();

    s_pim_queue_len += m_pim_buffer.size();

    auto col = try_issue_internal_rck();
    if (!col) {
      col = try_issue_pim_column();
    }
    if (!col) {
      col = try_issue_slot(SlotType::ColumnBus);
    }

    auto row = try_issue_pim_row_preq();
    if (!row) {
      row = try_issue_slot(SlotType::RowBus);
    }

    update_rck_state_on_issue(col);
    update_rck_state_on_issue(row);

    hbm_tick_epilogue();
  }

 protected:
  bool slot_matches(const Request& req, SlotType slot) const override {
    if (!HBMControllerBase::slot_matches(req, slot)) return false;
    if (m_rck_mode == RCKMode::StartWithRCKStrt && m_rck_state == RCKState::Stopped &&
        is_read_like(req.command)) {
      return false;
    }
    return true;
  }

 private:
  enum class RCKMode  { AlwaysOn, StartWithRead, StartWithRCKStrt };
  enum class RCKState { Stopped, Toggling };

  std::string m_rck_mode_str    = "always_on";
  RCKMode     m_rck_mode        = RCKMode::AlwaysOn;
  RCKState    m_rck_state       = RCKState::Toggling;
  int         m_rck_idle_threshold = 32;
  Clk_t       m_last_read_clk   = -1;

  int m_cmd_rckstrt   = -1;
  int m_cmd_rckstop   = -1;
  int m_cmd_rd        = -1;
  int m_cmd_rda       = -1;
  int m_channel_level = -1;

  size_t s_num_rckstrt_issued = 0;
  size_t s_num_rckstop_issued = 0;

  int m_cmd_actab    = -1;
  int m_cmd_macab    = -1;
  int m_cmd_macsb    = -1;
  int m_cmd_wr_bb     = -1;
  int m_cmd_rd_bb    = -1;
  int m_cmd_wr_rb    = -1;
  int m_cmd_rd_rb    = -1;
  int m_cmd_mv_rb     = -1;
  int m_cmd_mv_bb     = -1;
  int m_cmd_sfm      = -1;
  int m_cmd_act_func = -1;
  int m_cmd_setm     = -1;
  int m_cmd_seth     = -1;
  int m_cmd_barrier  = -1;

  std::vector<int> m_pim_final_cmds;
  ReqBuffer m_pim_buffer;
  size_t s_pim_queue_len = 0;


  std::optional<IssuedCommand> try_issue_pim_row_preq() {
    if (m_pim_buffer.size() == 0) return std::nullopt;
    if (m_priority_buffer.size() > 0) return std::nullopt;
    auto it = m_pim_buffer.begin();
    int preq_cmd = get_preq_command(it->final_command, it->addr_vec);
    if (!m_device.m_spec->command_meta[preq_cmd].is_row_command) return std::nullopt;
    if (!check_timing(preq_cmd, it->addr_vec)) return std::nullopt;

    m_device.issue_command(preq_cmd, it->addr_vec, m_clk);
    IssuedCommand issued{SlotType::RowBus, preq_cmd, it->addr_vec, m_clk};

    Request tmp_req(it->addr_vec, Request::Cmd, preq_cmd);
    m_rowpolicy->on_issue(tmp_req);
    for (auto* p : m_plugins) p->on_issue(tmp_req);

    return issued;
  }

  std::optional<IssuedCommand> try_issue_pim_column() {
    if (m_pim_buffer.size() == 0) return std::nullopt;

    auto it = m_pim_buffer.begin();
    it->command = get_preq_command(it->final_command, it->addr_vec);

    if (!m_device.m_spec->command_meta[it->command].is_column_command) {
      return std::nullopt;
    }

    if (!check_timing(it->command, it->addr_vec)) return std::nullopt;

    if (!it->is_stat_updated) update_request_stats(it);

    m_device.issue_command(it->command, it->addr_vec, m_clk);
    IssuedCommand issued{SlotType::ColumnBus, it->command, it->addr_vec, m_clk};

    m_rowpolicy->on_issue(*it);
    for (auto* p : m_plugins) p->on_issue(*it);

    if (it->command == it->final_command) {
      it->depart = m_clk;
      if (it->callback) it->callback(*it);
      m_pim_buffer.remove(it);
    }
    return issued;
  }

  bool is_read_like(int cmd) const {
    return cmd == m_cmd_rd || cmd == m_cmd_rda;
  }

  bool priority_buffer_contains(int cmd) {
    for (auto it = m_priority_buffer.begin(); it != m_priority_buffer.end(); ++it) {
      if (it->final_command == cmd) return true;
    }
    return false;
  }

  bool reads_waiting() {
    if (m_read_buffer.size() > 0) return true;
    for (auto it = m_active_buffer.begin(); it != m_active_buffer.end(); ++it) {
      if (it->type_id == Request::Type::Read) return true;
    }
    return false;
  }

  int get_rck_cmd() {
    if (m_rck_mode == RCKMode::AlwaysOn) return -1;
    if (m_rck_mode == RCKMode::StartWithRCKStrt && m_rck_state == RCKState::Stopped &&
        reads_waiting() && !priority_buffer_contains(m_cmd_rckstrt)) {
      return m_cmd_rckstrt;
    }
    if (m_rck_state == RCKState::Toggling && m_last_read_clk >= 0 && !reads_waiting() &&
        (m_clk - m_last_read_clk) >= m_rck_idle_threshold &&
        !priority_buffer_contains(m_cmd_rckstop)) {
      return m_cmd_rckstop;
    }
    return -1;
  }

  std::optional<IssuedCommand> try_issue_internal_rck() {
    int cmd = get_rck_cmd();
    if (cmd < 0) return std::nullopt;

    AddrVec_t addr_vec(m_device.m_spec->level_count, -1);
    addr_vec[m_channel_level] = m_channel_id;
    if (!check_timing(cmd, addr_vec)) return std::nullopt;

    Request req(addr_vec, Request::Cmd, cmd);
    req.command = cmd;
    m_device.issue_command(cmd, addr_vec, m_clk);
    IssuedCommand issued{SlotType::ColumnBus, cmd, addr_vec, m_clk};

    m_rowpolicy->on_issue(req);
    for (auto* p : m_plugins) p->on_issue(req);
    return issued;
  }

  void update_rck_state_on_issue(const std::optional<IssuedCommand>& issued) {
    if (!issued) return;
    if (issued->command == m_cmd_rckstrt) {
      m_rck_state = RCKState::Toggling;
      s_num_rckstrt_issued++;
    } else if (issued->command == m_cmd_rckstop) {
      m_rck_state = RCKState::Stopped;
      s_num_rckstop_issued++;
    } else if (is_read_like(issued->command)) {
      if (m_rck_mode == RCKMode::StartWithRead && m_rck_state == RCKState::Stopped) {
        m_rck_state = RCKState::Toggling;
      }
      m_last_read_clk = m_clk;
    }
  }
};

}
