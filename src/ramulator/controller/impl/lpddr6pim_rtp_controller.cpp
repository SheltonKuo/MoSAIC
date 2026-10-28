#include <cassert>
#include <fmt/format.h>
#include <stdexcept>

#include "ramulator/base/base.h"
#include "ramulator/controller/impl/lpddr_controller_base.h"
#include "ramulator/controller/impl/lpddr5pim_types.h"
#include "ramulator/controller/refresh/i_refresh_manager.h"
#include "ramulator/controller/rowpolicy/i_row_policy.h"
#include "ramulator/controller/scheduler/i_scheduler.h"
#include "ramulator/dram/dram_spec.h"

namespace Ramulator {

enum class LPDDR6RTPState {
  Idle, CpysbPending, WaitingLastSegment, LookaheadReady,
  Precharging, Activating1, Preloading, CpysbLaPending
};

enum class LPDDR6LAPriorityPolicy {
  Opportunistic,
  LookaheadFirst,
  MacabFirst
};

class LPDDR6PIMRTPController final : public LPDDRControllerBase {
  RAMULATOR_REGISTER_IMPLEMENTATION_DERIVED(
      IController, LPDDR6PIMRTPController, LPDDRControllerBase, "LPDDR6PIM_RTP")

 public:
  void init() override {
    LPDDRControllerBase::init();

    RAMULATOR_PARSE_PARAM(m_la_priority_str, std::string, "lookahead_priority")
        .default_val("macab_first");
    RAMULATOR_PARSE_PARAM(m_mini_tile_segments, int, "mini_tile_segments")
        .default_val(1);
    if (m_la_priority_str == "opportunistic") {
      m_la_priority = LPDDR6LAPriorityPolicy::Opportunistic;
    } else if (m_la_priority_str == "lookahead_first") {
      m_la_priority = LPDDR6LAPriorityPolicy::LookaheadFirst;
    } else if (m_la_priority_str == "macab_first") {
      m_la_priority = LPDDR6LAPriorityPolicy::MacabFirst;
    } else {
      throw std::runtime_error(
          "LPDDR6PIM_RTP: unsupported lookahead_priority '" +
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
          "LPDDR6PIM_RTP mini_tile_segments must be 1, 2, or 4 and divide "
          "the burst columns per row");
    }

    m_cmd_act1  = spec.get_command_id("ACT1");
    m_cmd_act2  = spec.get_command_id("ACT2");
    m_cmd_cas   = spec.get_command_id("CAS");
    m_cmd_rd    = spec.get_command_id("RD_S");
    m_cmd_wr    = spec.get_command_id("WR_S");
    m_cmd_rda   = spec.get_command_id("RDA_S");
    m_cmd_wra   = spec.get_command_id("WRA_S");

    m_nAAD              = spec.get_timing_value("nAAD");
    m_read_latency      = spec.get_timing_value("nRL");
    m_write_latency     = spec.get_timing_value("nWL");
    m_burst_cycles      = spec.get_timing_value("nBL_min");
    m_burst_cycles_long = spec.get_timing_value("nBL_min");
    m_nWCKPST           = spec.get_timing_value("nWCKPST");
    m_cas_deadline_guard = std::max(2, spec.get_timing_value("nCAS"));

    m_cmd_actab1   = spec.get_command_id("ACTAB1");
    m_cmd_actab2   = spec.get_command_id("ACTAB2");
    m_cmd_cpysb    = spec.get_command_id("CPYSB");
    m_cmd_cpysb_la = spec.get_command_id("CPYSB_LA");
    m_cmd_preab_la = spec.get_command_id("PREab_LA");

    m_cmd_macab    = spec.get_command_id("MACAB");
    m_cmd_macsb    = spec.get_command_id("MACSB");
    m_cmd_macpb    = spec.get_command_id("MACPB");
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
    m_pim_final_cmds[PIMRequestType::MAC_PB]    = m_cmd_macpb;
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
    m_la_state.assign(nb, LPDDR6RTPState::Idle);
    m_la_addr.resize(nb);
    m_la_next_addr.resize(nb);
    m_la_actab1_clk.assign(nb, -1);
    m_macab_count.assign(nb, 0);
    m_macab_expected.assign(nb, 0);
    m_last_macab_row.assign(nb, -1);
  }

  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    LPDDRControllerBase::setup(frontend, memory_system);
    m_stats.add("pim_queue_len", s_pim_queue_len);
  }

  bool send(Request& req) override {
    if (req.type_id == Request::Type::Read || req.type_id == Request::Type::Write)
      return LPDDRControllerBase::send(req);
    if (req.type_id < 0 || req.type_id >= PIMRequestType::COUNT ||
        m_pim_final_cmds[req.type_id] < 0)
      throw std::runtime_error(fmt::format(
          "LPDDR6PIMRTPController: unknown PIM type_id {}", req.type_id));
    m_addr_mapper->apply(req);
    req.addr_vec[0] = m_channel_id;
    req.final_command = m_pim_final_cmds[req.type_id];
    req.arrive = m_clk;
    bool ok = m_pim_buffer.enqueue(req);
    if (!ok) req.arrive = -1;
    return ok;
  }

  void tick() override {
    tick_prologue();
    m_refresh->tick();
    s_pim_queue_len += m_pim_buffer.size();
    m_rowpolicy->pre_schedule();
    for (auto* p : m_plugins) p->pre_schedule();

    Candidate urgent_act2 = pick_urgent_act2();

    if (m_cas_issued) {
      if (check_timing(m_cas_req_it->command, m_cas_req_it->addr_vec)) {
        m_cas_issued = false;
        if (m_wck_sync_mode == WCKSyncMode::NeedSync)
          extend_wck_expiry(m_cas_req_it->command);
        s_cas_issued++;
        if (!m_cas_req_it->is_stat_updated) update_request_stats(m_cas_req_it);
        m_device.issue_command(m_cas_req_it->command, m_cas_req_it->addr_vec, m_clk);
        m_rowpolicy->on_issue(*m_cas_req_it);
        for (auto* p : m_plugins) p->on_issue(*m_cas_req_it);
        if (m_cas_req_it->command == m_cas_req_it->final_command)
          retire_request(m_cas_req_it, *m_cas_buffer);
      }
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) p->post_schedule();
      return;
    }

    if (!has_rtp_actab2_pending() && has_pending_act2()) {
      Candidate pending_act2 = pick_deferred_act2();
      if (pending_act2.valid) {
        issue_owned_act2(pending_act2, Act2IssueKind::Deferred);
      }
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) p->post_schedule();
      return;
    }

    if (try_issue_la_copy()) {
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) p->post_schedule();
      return;
    }

    if (urgent_act2.valid && !has_rtp_actab2_pending()) {
      issue_owned_act2(urgent_act2, Act2IssueKind::Urgent);
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) p->post_schedule();
      return;
    }

    Candidate cand = pick_priority_if();

    if (!cand.valid &&
        m_la_priority == LPDDR6LAPriorityPolicy::LookaheadFirst &&
        try_issue_la_pipeline()) {
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) p->post_schedule();
      return;
    }

    if (!cand.valid && m_la_priority == LPDDR6LAPriorityPolicy::MacabFirst) {
      cand = pick_ready_pim(true);
      if (!cand.valid && try_issue_la_pipeline()) {
        m_rowpolicy->post_schedule();
        for (auto* p : m_plugins) p->post_schedule();
        return;
      }
    }

    if (!cand.valid) cand = pick_ready_pim(false);

    if (!cand.valid &&
        m_la_priority == LPDDR6LAPriorityPolicy::Opportunistic &&
        try_issue_la_pipeline()) {
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) p->post_schedule();
      return;
    }
    if (!cand.valid) cand = select_normal_candidate();
    if (!cand.valid) cand = pick_cas_lookahead_candidate();
    if (!cand.valid) {
      Candidate deferred = pick_deferred_act2();
      if (deferred.valid) issue_owned_act2(deferred, Act2IssueKind::Deferred);
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) p->post_schedule();
      return;
    }

    if (cand.buffer == &m_activating_buffer)
      issue_owned_act2(cand, Act2IssueKind::Urgent);
    else if (cand.buffer == &m_pim_buffer)
      issue_pim_candidate(cand);
    else if (!try_issue_cas_sync(cand))
      issue_standard_candidate(cand);

    m_rowpolicy->post_schedule();
    for (auto* p : m_plugins) p->post_schedule();
  }

 private:
  int m_cmd_actab1   = -1, m_cmd_actab2   = -1;
  int m_cmd_cpysb    = -1, m_cmd_cpysb_la = -1, m_cmd_preab_la = -1;
  int m_cmd_macab = -1;
  int m_cmd_macsb    = -1, m_cmd_macpb    = -1;
  int m_cmd_wr_bb    = -1, m_cmd_rd_bb    = -1;
  int m_cmd_wr_rb    = -1, m_cmd_rd_rb    = -1;
  int m_cmd_mv_rb    = -1, m_cmd_mv_bb    = -1;
  int m_cmd_sfm      = -1, m_cmd_act_func = -1;
  int m_cmd_setm     = -1, m_cmd_seth     = -1;
  int m_cmd_barrier  = -1;
  int m_column_level = -1;
  int m_columns_per_row = -1;
  int m_mini_tile_segments = 1;

  std::vector<int>           m_pim_final_cmds;
  ReqBuffer                  m_pim_buffer;
  size_t                     s_pim_queue_len = 0;

  std::vector<LPDDR6RTPState> m_la_state;
  std::vector<AddrVec_t>      m_la_addr;
  std::vector<AddrVec_t>      m_la_next_addr;
  std::vector<Clk_t>          m_la_actab1_clk;
  std::vector<int>            m_macab_count;
  std::vector<int>            m_macab_expected;
  std::vector<int>            m_last_macab_row;

  std::string                  m_la_priority_str;
  LPDDR6LAPriorityPolicy       m_la_priority = LPDDR6LAPriorityPolicy::MacabFirst;

  bool is_macab(int cmd) const { return cmd == m_cmd_macab; }

  bool is_last_column_segment(const AddrVec_t& addr_vec) const {
    const int columns_per_segment = m_columns_per_row / m_mini_tile_segments;
    return addr_vec[m_column_level] >=
           m_columns_per_row - columns_per_segment;
  }

  void finish_secondary_copy(size_t fid, const AddrVec_t& addr_vec) {
    m_la_state[fid] = is_last_column_segment(addr_vec)
                          ? LPDDR6RTPState::LookaheadReady
                          : LPDDR6RTPState::WaitingLastSegment;
  }

  void issue_internal_la_command(int cmd, const AddrVec_t& addr_vec) {
    m_device.issue_command(cmd, addr_vec, m_clk);
    Request req(addr_vec, Request::Cmd, cmd);
    req.command = cmd;
    m_rowpolicy->on_issue(req);
    for (auto* p : m_plugins) p->on_issue(req);
  }

  Candidate pick_ready_pim(bool macab_only) {
    Candidate cand = pick_best_ready_from(m_pim_buffer, [&](const Request& req) {
      return is_pim_request_allowed(req) &&
             (!macab_only || is_macab(req.final_command));
    });
    if (cand.valid) {
      cand.it->command = get_preq_command(cand.it->final_command, cand.it->addr_vec);
      if (!check_timing(cand.it->command, cand.it->addr_vec)) cand.valid = false;
    }
    return cand;
  }

  bool has_rtp_actab2_pending() const {
    for (LPDDR6RTPState state : m_la_state) {
      if (state == LPDDR6RTPState::Activating1) return true;
    }
    return false;
  }

  bool try_issue_rtp_actab2() {
    for (size_t fid = 0; fid < m_la_state.size(); fid++) {
      if (m_la_state[fid] != LPDDR6RTPState::Activating1) continue;
      if (!check_timing(m_cmd_actab2, m_la_next_addr[fid])) continue;

      issue_internal_la_command(m_cmd_actab2, m_la_next_addr[fid]);
      auto s = scan_pim_buffer(m_la_addr[fid]);
      m_la_state[fid] = (s.same_count == 0)
                            ? LPDDR6RTPState::CpysbLaPending
                            : LPDDR6RTPState::Preloading;
      return true;
    }
    return false;
  }

  struct RowScan { int same_count; bool next_found; AddrVec_t next_addr; };
  RowScan scan_pim_buffer(const AddrVec_t& cur) {
    int rank_lvl = m_device.m_spec->get_level_id("Rank");
    int row_lvl = m_device.m_spec->get_level_id("Row");
    int cur_rank = cur[rank_lvl];
    int cur_row = cur[row_lvl];
    RowScan s{0, false, {}};
    for (auto it = m_pim_buffer.begin(); it != m_pim_buffer.end(); ++it) {
      if (!is_macab(it->final_command)) continue;
      if (it->addr_vec[rank_lvl] != cur_rank) continue;
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
    LPDDR6RTPState state = m_la_state[fid];
    if (state == LPDDR6RTPState::Idle) return true;
    if (state == LPDDR6RTPState::CpysbPending) return false;

    int row_lvl = m_device.m_spec->get_level_id("Row");
    return req.addr_vec[row_lvl] == m_la_addr[fid][row_lvl];
  }

  bool try_issue_la_copy() {
    for (size_t fid = 0; fid < m_la_state.size(); fid++) {
      if (m_la_state[fid] == LPDDR6RTPState::CpysbPending) {
        if (!check_timing(m_cmd_cpysb, m_la_addr[fid])) continue;
        issue_internal_la_command(m_cmd_cpysb, m_la_addr[fid]);
        finish_secondary_copy(fid, m_la_addr[fid]);
        return true;
      }

      if (m_la_state[fid] == LPDDR6RTPState::CpysbLaPending) {
        if (!check_timing(m_cmd_cpysb_la, m_la_next_addr[fid])) continue;
        issue_internal_la_command(m_cmd_cpysb_la, m_la_next_addr[fid]);
        m_la_addr[fid] = m_la_next_addr[fid];
        m_la_next_addr[fid].clear();
        finish_secondary_copy(fid, m_la_addr[fid]);
        return true;
      }
    }
    return false;
  }

  bool try_issue_la_pipeline() {
    for (size_t fid = 0; fid < m_la_state.size(); fid++) {
      switch (m_la_state[fid]) {

        case LPDDR6RTPState::WaitingLastSegment: {
          auto s = scan_pim_buffer(m_la_addr[fid]);
          if (s.same_count != 0 || !s.next_found) continue;
          m_la_state[fid] = LPDDR6RTPState::LookaheadReady;
          [[fallthrough]];
        }

        case LPDDR6RTPState::LookaheadReady: {
          if (!check_timing(m_cmd_preab_la, m_la_addr[fid])) continue;
          issue_internal_la_command(m_cmd_preab_la, m_la_addr[fid]);
          m_la_state[fid] = LPDDR6RTPState::Precharging;
          return true;
        }

        case LPDDR6RTPState::Precharging: {
          if (m_la_next_addr[fid].empty()) {
            auto s = scan_pim_buffer(m_la_addr[fid]);
            if (!s.next_found) continue;
            m_la_next_addr[fid] = s.next_addr;
          }
          if (!check_timing(m_cmd_actab1, m_la_next_addr[fid])) continue;
          issue_internal_la_command(m_cmd_actab1, m_la_next_addr[fid]);
          m_la_state[fid] = LPDDR6RTPState::Activating1;
          return true;
        }

        case LPDDR6RTPState::Activating1: {
          return try_issue_rtp_actab2();
        }

        case LPDDR6RTPState::Preloading: {
          continue;
        }

        default: break;
      }
    }
    return false;
  }

  void issue_pim_candidate(Candidate& cand) {
    if (!cand.it->is_stat_updated) update_request_stats(cand.it);

    int cmd = cand.it->command;
    int fid = m_device.get_flat_bank_id(cand.it->addr_vec);

    m_device.issue_command(cmd, cand.it->addr_vec, m_clk);
    m_rowpolicy->on_issue(*cand.it);
    for (auto* p : m_plugins) p->on_issue(*cand.it);

    if (cmd == m_cmd_actab1) {
      m_la_actab1_clk[fid] = m_clk;
    }

    if (cmd == m_cmd_actab2 && m_la_state[fid] == LPDDR6RTPState::Idle) {
      m_la_addr[fid]  = cand.it->addr_vec;
      m_la_state[fid] = LPDDR6RTPState::CpysbPending;
    }

    if (cmd == m_cmd_cpysb && m_la_state[fid] == LPDDR6RTPState::CpysbPending) {
      finish_secondary_copy(fid, cand.it->addr_vec);
    }

    if (is_macab(cmd) &&
        m_la_state[fid] == LPDDR6RTPState::WaitingLastSegment) {
      int row_lvl = m_device.m_spec->get_level_id("Row");
      if (cand.it->addr_vec[row_lvl] == m_la_addr[fid][row_lvl] &&
          is_last_column_segment(cand.it->addr_vec)) {
        m_la_state[fid] = LPDDR6RTPState::LookaheadReady;
      }
    }

    if (is_macab(cmd) && m_la_state[fid] == LPDDR6RTPState::Preloading) {
      int row_lvl = m_device.m_spec->get_level_id("Row");
      int cur_row = m_la_addr[fid][row_lvl];
      if (cand.it->addr_vec[row_lvl] == cur_row) {
        auto s = scan_pim_buffer(cand.it->addr_vec);
        if (s.same_count <= 1) {
          m_la_state[fid] = LPDDR6RTPState::CpysbLaPending;
        }
      }
    }

    if (cand.it->command == cand.it->final_command) {
      cand.it->depart = m_clk;
      if (cand.it->callback) cand.it->callback(*cand.it);
      m_pim_buffer.remove(cand.it);
    }
  }
};

}
