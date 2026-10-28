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

class LPDDR6PIMController final : public LPDDRControllerBase {
  RAMULATOR_REGISTER_IMPLEMENTATION_DERIVED(
      IController, LPDDR6PIMController, LPDDRControllerBase, "LPDDR6PIM")

 public:
  void init() override {
    LPDDRControllerBase::init();

    const auto& spec = *m_device.m_spec;

    m_cmd_act1  = spec.get_command_id("ACT1");
    m_cmd_act2  = spec.get_command_id("ACT2");
    m_cmd_cas   = spec.get_command_id("CAS");
    m_cmd_rd    = spec.get_command_id("RD_S");
    m_cmd_wr    = spec.get_command_id("WR_S");
    m_cmd_rda   = spec.get_command_id("RDA_S");
    m_cmd_wra   = spec.get_command_id("WRA_S");

    m_nAAD             = spec.get_timing_value("nAAD");
    m_read_latency     = spec.get_timing_value("nRL");
    m_write_latency    = spec.get_timing_value("nWL");
    m_burst_cycles     = spec.get_timing_value("nBL_min");
    m_burst_cycles_long = spec.get_timing_value("nBL_min");
    m_nWCKPST          = spec.get_timing_value("nWCKPST");
    m_cas_deadline_guard = std::max(2, spec.get_timing_value("nCAS"));

    m_cmd_actab1   = spec.get_command_id("ACTAB1");
    m_cmd_actab2   = spec.get_command_id("ACTAB2");
    m_cmd_macab    = spec.get_command_id("MACAB");
    m_cmd_macsb    = spec.get_command_id("MACSB");
    m_cmd_macpb    = spec.get_command_id("MACPB");
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
  }

  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    LPDDRControllerBase::setup(frontend, memory_system);
    m_stats.add("pim_queue_len", s_pim_queue_len);
  }

  bool send(Request& req) override {
    if (req.type_id == Request::Type::Read || req.type_id == Request::Type::Write) {
      return LPDDRControllerBase::send(req);
    }

    if (req.type_id < 0 || req.type_id >= PIMRequestType::COUNT ||
        m_pim_final_cmds[req.type_id] < 0) {
      throw std::runtime_error(fmt::format(
          "LPDDR6PIMController: unknown PIM request type_id {}", req.type_id));
    }

    m_addr_mapper->apply(req);
    req.addr_vec[0] = m_channel_id;
    req.final_command = m_pim_final_cmds[req.type_id];
    req.arrive = m_clk;

    bool ok = m_pim_buffer.enqueue(req);
    if (!ok) {
      req.arrive = -1;
    }
    return ok;
  }

  void tick() override {
    tick_prologue();
    m_refresh->tick();

    s_pim_queue_len += m_pim_buffer.size();

    m_rowpolicy->pre_schedule();
    for (auto* p : m_plugins) {
      p->pre_schedule();
    }

    Candidate urgent_act2 = pick_urgent_act2();

    if (m_cas_issued) {
      if (check_timing(m_cas_req_it->command, m_cas_req_it->addr_vec)) {
        m_cas_issued = false;
        if (m_wck_sync_mode == WCKSyncMode::NeedSync) {
          extend_wck_expiry(m_cas_req_it->command);
        }
        s_cas_issued++;

        if (!m_cas_req_it->is_stat_updated) {
          update_request_stats(m_cas_req_it);
        }
        m_device.issue_command(m_cas_req_it->command, m_cas_req_it->addr_vec, m_clk);
        m_rowpolicy->on_issue(*m_cas_req_it);
        for (auto* p : m_plugins) {
          p->on_issue(*m_cas_req_it);
        }

        if (m_cas_req_it->command == m_cas_req_it->final_command) {
          retire_request(m_cas_req_it, *m_cas_buffer);
        }
      }
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) {
        p->post_schedule();
      }
      return;
    }

    if (urgent_act2.valid) {
      issue_owned_act2(urgent_act2, Act2IssueKind::Urgent);
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) {
        p->post_schedule();
      }
      return;
    }

    Candidate cand = pick_priority_if();

    if (!cand.valid) {
      cand = pick_best_ready_from(m_pim_buffer, {});
      if (cand.valid) {
        cand.it->command = get_preq_command(cand.it->final_command, cand.it->addr_vec);
        if (!check_timing(cand.it->command, cand.it->addr_vec)) {
          cand.valid = false;
        }
      }
    }

    if (!cand.valid) {
      cand = select_normal_candidate();
    }
    if (!cand.valid) {
      cand = pick_cas_lookahead_candidate();
    }
    if (!cand.valid) {
      Candidate deferred = pick_deferred_act2();
      if (deferred.valid) {
        issue_owned_act2(deferred, Act2IssueKind::Deferred);
      }
      m_rowpolicy->post_schedule();
      for (auto* p : m_plugins) {
        p->post_schedule();
      }
      return;
    }

    if (cand.buffer == &m_activating_buffer) {
      issue_owned_act2(cand, Act2IssueKind::Urgent);
    } else if (cand.buffer == &m_pim_buffer) {
      issue_pim_candidate(cand);
    } else if (!try_issue_cas_sync(cand)) {
      issue_standard_candidate(cand);
    }

    m_rowpolicy->post_schedule();
    for (auto* p : m_plugins) {
      p->post_schedule();
    }
  }

 private:
  int m_cmd_actab1   = -1;
  int m_cmd_actab2   = -1;
  int m_cmd_macab    = -1;
  int m_cmd_macsb    = -1;
  int m_cmd_macpb    = -1;
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

  void issue_pim_candidate(Candidate& cand) {
    if (!cand.it->is_stat_updated) {
      update_request_stats(cand.it);
    }

    m_device.issue_command(cand.it->command, cand.it->addr_vec, m_clk);
    m_rowpolicy->on_issue(*cand.it);
    for (auto* p : m_plugins) {
      p->on_issue(*cand.it);
    }

    if (cand.it->command == cand.it->final_command) {
      cand.it->depart = m_clk;
      if (cand.it->callback) {
        cand.it->callback(*cand.it);
      }
      m_pim_buffer.remove(cand.it);
    }
  }
};

}
