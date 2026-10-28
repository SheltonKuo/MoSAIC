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

enum class GDDR7RTPState {
  Idle, CpysbPending, WaitingLastSegment, LookaheadReady,
  Precharging, Preloading, CpysbLaPending
};

enum class GDDR7LAPriorityPolicy {
  Opportunistic,
  LookaheadFirst,
  MacabFirst
};

class GDDR7PIMRTPController final : public HBMControllerBase {
  RAMULATOR_REGISTER_IMPLEMENTATION_DERIVED(
      IController, GDDR7PIMRTPController, HBMControllerBase, "GDDR7PIM_RTP")

 public:
  void init() override {
    HBMControllerBase::init();

    RAMULATOR_PARSE_PARAM(m_rck_mode_str, std::string, "rck_mode").default_val("always_on");
    RAMULATOR_PARSE_PARAM(m_rck_idle_threshold, int, "rck_idle_threshold").default_val(32);
    RAMULATOR_PARSE_PARAM(m_la_priority_str, std::string, "lookahead_priority")
        .default_val("macab_first");
    RAMULATOR_PARSE_PARAM(m_mini_tile_segments, int, "mini_tile_segments")
        .default_val(1);

    if      (m_rck_mode_str == "always_on")          m_rck_mode = RCKMode::AlwaysOn;
    else if (m_rck_mode_str == "start_with_read")     m_rck_mode = RCKMode::StartWithRead;
    else if (m_rck_mode_str == "start_with_rckstrt")  m_rck_mode = RCKMode::StartWithRCKStrt;
    else throw std::runtime_error(
        "GDDR7PIM_RTP: unsupported rck_mode '" + m_rck_mode_str + "'");

    if (m_la_priority_str == "opportunistic") {
      m_la_priority = GDDR7LAPriorityPolicy::Opportunistic;
    } else if (m_la_priority_str == "lookahead_first") {
      m_la_priority = GDDR7LAPriorityPolicy::LookaheadFirst;
    } else if (m_la_priority_str == "macab_first") {
      m_la_priority = GDDR7LAPriorityPolicy::MacabFirst;
    } else {
      throw std::runtime_error(
          "GDDR7PIM_RTP: unsupported lookahead_priority '" +
          m_la_priority_str + "'");
    }

    const auto& spec = *m_device.m_spec;
    m_column_level = spec.get_level_id("Column");
    m_columns_per_row = spec.get_level_size("Column") /
                        spec.internal_prefetch_size;
    if ((m_mini_tile_segments != 1 && m_mini_tile_segments != 2 &&
         m_mini_tile_segments != 4) ||
        m_columns_per_row < m_mini_tile_segments ||
        m_columns_per_row % m_mini_tile_segments != 0) {
      throw std::runtime_error(
          "GDDR7PIM_RTP mini_tile_segments must be 1, 2, or 4 and divide "
          "the burst columns per row");
    }

    m_cmd_rckstrt   = spec.get_command_id("RCKSTRT");
    m_cmd_rckstop   = spec.get_command_id("RCKSTOP");
    m_cmd_rd        = spec.get_command_id("RD");
    m_cmd_rda       = spec.get_command_id("RDA");
    m_channel_level = spec.get_level_id("Channel");

    m_rck_state = (m_rck_mode == RCKMode::AlwaysOn) ? RCKState::Toggling : RCKState::Stopped;

    m_cmd_actab    = spec.get_command_id("ACTAB");
    m_cmd_cpysb    = spec.get_command_id("CPYSB");
    m_cmd_cpysb_la = spec.get_command_id("CPYSB_LA");
    m_cmd_preab_la = spec.get_command_id("PREab_LA");
    m_cmd_macab    = spec.get_command_id("MACAB");
    m_cmd_macsb    = spec.get_command_id("MACSB");
    m_cmd_wr_bb    = spec.get_command_id("WR_BB");
    m_cmd_rd_bb    = spec.get_command_id("RD_BB");
    m_cmd_wr_rb    = spec.get_command_id("WR_RB");
    m_cmd_rd_rb    = spec.get_command_id("RD_RB");
    m_cmd_mv_rb    = spec.get_command_id("MV_RB");
    m_cmd_mv_bb    = spec.get_command_id("MV_BB");
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

    size_t nb = m_device.m_bank_nodes.size();
    m_la_state.assign(nb, GDDR7RTPState::Idle);
    m_la_addr.resize(nb);
    m_la_next_addr.resize(nb);
    m_cpysb_pending.assign(nb, false);
    m_cpysb_addr.resize(nb);
  }

  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    HBMControllerBase::setup(frontend, memory_system);
    m_stats.add("pim_queue_len",      s_pim_queue_len);
    m_stats.add("num_rckstrt_issued", s_num_rckstrt_issued);
    m_stats.add("num_rckstop_issued", s_num_rckstop_issued);
  }

  bool send(Request& req) override {
    if (req.type_id == Request::Type::Read || req.type_id == Request::Type::Write)
      return ControllerBase::send(req);
    if (req.type_id < 0 || req.type_id >= PIMRequestType::COUNT ||
        m_pim_final_cmds[req.type_id] < 0)
      throw std::runtime_error(fmt::format(
          "GDDR7PIMRTPController: unknown or unsupported PIM request type_id {}", req.type_id));
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
    reconcile_rtp_state_after_external_close();

    s_pim_queue_len += m_pim_buffer.size();

    auto col = try_issue_internal_rck();
    if (!col && m_la_priority == GDDR7LAPriorityPolicy::MacabFirst)
      col = try_issue_pim_column(true);
    if (!col) col = try_issue_rtp_column();
    if (!col) col = try_issue_pim_column(false);
    if (!col) col = try_issue_slot(SlotType::ColumnBus);

    auto row = try_issue_rtp_row();
    if (!row) row = try_issue_pim_row_preq();
    if (!row) row = try_issue_slot(SlotType::RowBus);

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

  std::string                m_la_priority_str = "macab_first";
  GDDR7LAPriorityPolicy      m_la_priority = GDDR7LAPriorityPolicy::MacabFirst;

  int m_cmd_rckstrt   = -1;
  int m_cmd_rckstop   = -1;
  int m_cmd_rd        = -1;
  int m_cmd_rda       = -1;
  int m_channel_level = -1;

  size_t s_num_rckstrt_issued = 0;
  size_t s_num_rckstop_issued = 0;

  int m_cmd_actab    = -1;
  int m_cmd_cpysb    = -1, m_cmd_cpysb_la = -1, m_cmd_preab_la = -1;
  int m_cmd_macab = -1;
  int m_cmd_macsb    = -1;
  int m_cmd_wr_bb    = -1, m_cmd_rd_bb    = -1;
  int m_cmd_wr_rb    = -1, m_cmd_rd_rb    = -1;
  int m_cmd_mv_rb    = -1, m_cmd_mv_bb    = -1;
  int m_cmd_sfm      = -1, m_cmd_act_func = -1;
  int m_cmd_setm     = -1, m_cmd_seth     = -1;
  int m_cmd_barrier  = -1;
  int m_column_level = -1;
  int m_columns_per_row = -1;
  int m_mini_tile_segments = 1;

  std::vector<int>          m_pim_final_cmds;
  ReqBuffer                 m_pim_buffer;
  size_t                    s_pim_queue_len = 0;

  std::vector<GDDR7RTPState> m_la_state;
  std::vector<AddrVec_t>     m_la_addr;
  std::vector<AddrVec_t>     m_la_next_addr;
  std::vector<bool>          m_cpysb_pending;
  std::vector<AddrVec_t>     m_cpysb_addr;

  bool is_macab(int cmd) const { return cmd == m_cmd_macab; }

  bool is_last_column_segment(const AddrVec_t& addr_vec) const {
    const int columns_per_segment = m_columns_per_row / m_mini_tile_segments;
    return addr_vec[m_column_level] >=
           m_columns_per_row - columns_per_segment;
  }

  void finish_secondary_copy(size_t fid, const AddrVec_t& addr_vec) {
    m_la_state[fid] = is_last_column_segment(addr_vec)
                          ? GDDR7RTPState::LookaheadReady
                          : GDDR7RTPState::WaitingLastSegment;
  }

  void issue_internal_rtp_command(int cmd, const AddrVec_t& addr_vec) {
    m_device.issue_command(cmd, addr_vec, m_clk);
    Request req(addr_vec, Request::Cmd, cmd);
    req.command = cmd;
    m_rowpolicy->on_issue(req);
    for (auto* p : m_plugins) p->on_issue(req);
  }

  void reconcile_rtp_state_after_external_close() {
    for (size_t fid = 0; fid < m_la_state.size(); fid++) {
      auto* bank = m_device.m_bank_nodes[fid];
      if (m_la_state[fid] == GDDR7RTPState::Idle ||
          bank->m_state != m_device.m_spec->get_state_id("Closed") ||
          bank->m_secondary_buffer_ready) {
        continue;
      }
      m_la_state[fid] = GDDR7RTPState::Idle;
      m_la_addr[fid].clear();
      m_la_next_addr[fid].clear();
      m_cpysb_pending[fid] = false;
      m_cpysb_addr[fid].clear();
    }
  }

  struct RowScan { int same_count; bool next_found; AddrVec_t next_addr; };
  RowScan scan_pim_buffer(const AddrVec_t& cur) {
    int row_lvl = m_device.m_spec->get_level_id("Row");
    int cur_row = cur[row_lvl];
    RowScan s{0, false, {}};
    for (auto it = m_pim_buffer.begin(); it != m_pim_buffer.end(); ++it) {
      if (!is_macab(it->final_command)) continue;
      if (it->addr_vec[row_lvl] == cur_row)
        s.same_count++;
      else if (!s.next_found) {
        s.next_found = true;
        s.next_addr  = it->addr_vec;
      }
    }
    return s;
  }

  bool is_pim_request_allowed(const Request& req) {
    if (!is_macab(req.final_command)) return true;

    int fid = m_device.get_flat_bank_id(req.addr_vec);
    GDDR7RTPState state = m_la_state[fid];
    if (state == GDDR7RTPState::Idle) return true;
    if (state == GDDR7RTPState::CpysbPending) return false;

    int row_lvl = m_device.m_spec->get_level_id("Row");
    return req.addr_vec[row_lvl] == m_la_addr[fid][row_lvl];
  }


  std::optional<IssuedCommand> try_issue_rtp_row() {
    if (m_priority_buffer.size() > 0) return std::nullopt;

    for (size_t fid = 0; fid < m_la_state.size(); fid++) {
      if (m_cpysb_pending[fid]) {
        if (!check_timing(m_cmd_cpysb, m_cpysb_addr[fid])) continue;
        AddrVec_t fired_addr = m_cpysb_addr[fid];
        issue_internal_rtp_command(m_cmd_cpysb, fired_addr);
        m_cpysb_pending[fid] = false;
        if (m_la_state[fid] == GDDR7RTPState::CpysbPending)
          finish_secondary_copy(fid, fired_addr);
        return IssuedCommand{SlotType::RowBus, m_cmd_cpysb, fired_addr, m_clk};
      }

      if (m_la_state[fid] == GDDR7RTPState::WaitingLastSegment) {
        auto s = scan_pim_buffer(m_la_addr[fid]);
        if (s.same_count == 0 && s.next_found)
          m_la_state[fid] = GDDR7RTPState::LookaheadReady;
      }

      if (m_la_state[fid] == GDDR7RTPState::LookaheadReady) {
        auto s = scan_pim_buffer(m_la_addr[fid]);
        if (!s.next_found) continue;
        m_la_next_addr[fid] = s.next_addr;
        if (!check_timing(m_cmd_preab_la, m_la_addr[fid])) continue;
        issue_internal_rtp_command(m_cmd_preab_la, m_la_addr[fid]);
        m_la_state[fid] = GDDR7RTPState::Precharging;
        return IssuedCommand{SlotType::RowBus, m_cmd_preab_la, m_la_addr[fid], m_clk};
      }

      if (m_la_state[fid] == GDDR7RTPState::Precharging) {
        auto s = scan_pim_buffer(m_la_addr[fid]);
        if (m_la_next_addr[fid].empty()) continue;
        if (!check_timing(m_cmd_actab, m_la_next_addr[fid])) continue;
        issue_internal_rtp_command(m_cmd_actab, m_la_next_addr[fid]);
        AddrVec_t next_addr = m_la_next_addr[fid];
        m_la_state[fid] = (s.same_count == 0)
                              ? GDDR7RTPState::CpysbLaPending
                              : GDDR7RTPState::Preloading;
        return IssuedCommand{SlotType::RowBus, m_cmd_actab, next_addr, m_clk};
      }
    }
    return std::nullopt;
  }

  std::optional<IssuedCommand> try_issue_rtp_column() {
    for (size_t fid = 0; fid < m_la_state.size(); fid++) {
      if (m_la_state[fid] != GDDR7RTPState::CpysbLaPending) continue;
      if (!check_timing(m_cmd_cpysb_la, m_la_next_addr[fid])) continue;
      AddrVec_t next_addr = m_la_next_addr[fid];
      issue_internal_rtp_command(m_cmd_cpysb_la, next_addr);
      m_la_addr[fid] = next_addr;
      finish_secondary_copy(fid, next_addr);
      return IssuedCommand{SlotType::ColumnBus, m_cmd_cpysb_la, next_addr, m_clk};
    }
    return std::nullopt;
  }

  std::optional<IssuedCommand> try_issue_pim_row_preq() {
    if (m_pim_buffer.size() == 0) return std::nullopt;
    if (m_priority_buffer.size() > 0) return std::nullopt;
    auto it = m_pim_buffer.begin();
    if (!is_pim_request_allowed(*it)) return std::nullopt;
    int preq_cmd = get_preq_command(it->final_command, it->addr_vec);
    if (!m_device.m_spec->command_meta[preq_cmd].is_row_command) return std::nullopt;
    if (!check_timing(preq_cmd, it->addr_vec)) return std::nullopt;

    m_device.issue_command(preq_cmd, it->addr_vec, m_clk);
    IssuedCommand issued{SlotType::RowBus, preq_cmd, it->addr_vec, m_clk};

    Request tmp_req(it->addr_vec, Request::Cmd, preq_cmd);
    tmp_req.command = preq_cmd;
    m_rowpolicy->on_issue(tmp_req);
    for (auto* p : m_plugins) p->on_issue(tmp_req);

    if (preq_cmd == m_cmd_actab) {
      int fid = m_device.get_flat_bank_id(it->addr_vec);
      if (m_la_state[fid] == GDDR7RTPState::Idle) {
        m_la_addr[fid]       = it->addr_vec;
        m_la_state[fid]      = GDDR7RTPState::CpysbPending;
        m_cpysb_pending[fid] = true;
        m_cpysb_addr[fid]    = it->addr_vec;
      }
    }
    return issued;
  }

  std::optional<IssuedCommand> try_issue_pim_column(bool macab_only) {
    if (m_pim_buffer.size() == 0) return std::nullopt;

    Candidate cand = pick_best_ready_from(m_pim_buffer, [&](const Request& req) {
      return is_pim_request_allowed(req) &&
             m_device.m_spec->command_meta[req.command].is_column_command &&
             (!macab_only || is_macab(req.final_command));
    });
    if (!cand.valid) return std::nullopt;
    auto it = cand.it;

    if (!it->is_stat_updated) update_request_stats(it);

    m_device.issue_command(it->command, it->addr_vec, m_clk);
    IssuedCommand issued{SlotType::ColumnBus, it->command, it->addr_vec, m_clk};

    m_rowpolicy->on_issue(*it);
    for (auto* p : m_plugins) p->on_issue(*it);

    if (is_macab(it->command)) {
      int fid = m_device.get_flat_bank_id(it->addr_vec);
      if (m_la_state[fid] == GDDR7RTPState::WaitingLastSegment) {
        int row_lvl = m_device.m_spec->get_level_id("Row");
        if (it->addr_vec[row_lvl] == m_la_addr[fid][row_lvl] &&
            is_last_column_segment(it->addr_vec)) {
          m_la_state[fid] = GDDR7RTPState::LookaheadReady;
        }
      }
      if (m_la_state[fid] == GDDR7RTPState::Preloading) {
        int row_lvl = m_device.m_spec->get_level_id("Row");
        int cur_row = m_la_addr[fid][row_lvl];
        if (it->addr_vec[row_lvl] == cur_row) {
          auto s = scan_pim_buffer(it->addr_vec);
          if (s.same_count <= 1) {
            m_la_state[fid] = GDDR7RTPState::CpysbLaPending;
          }
        }
      }
    }

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
