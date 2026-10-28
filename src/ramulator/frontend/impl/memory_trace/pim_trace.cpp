#include <filesystem>
#include <fmt/format.h>
#include <fstream>

#include "ramulator/base/param.h"
#include "ramulator/controller/impl/lpddr5pim_types.h"
#include "ramulator/frontend/i_frontend.h"

namespace Ramulator {

namespace fs = std::filesystem;

class PIMTrace : public IFrontEnd, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IFrontEnd, PIMTrace, "PIMTrace")


 private:
  struct TraceEntry {
    int type_id;
    Addr_t addr;
  };
  std::vector<TraceEntry> m_trace;

  size_t m_trace_length = 0;
  size_t m_curr_idx = 0;
  size_t m_issued = 0;
  size_t m_completed = 0;
  std::string m_trace_path;
  unsigned int m_max_issue_per_cycle = 1;
  bool m_drain_after_trace = false;
  std::vector<std::vector<TraceEntry>> m_channel_traces;
  std::vector<size_t> m_channel_indices;
  size_t m_next_channel = 0;

 public:
  void init() override {
    RAMULATOR_PARSE_PARAM(m_clock_ratio, unsigned int, "clock_ratio").required();
    RAMULATOR_PARSE_PARAM(m_trace_path, std::string, "path").required();
    RAMULATOR_PARSE_PARAM(m_max_issue_per_cycle, unsigned int, "max_issue_per_cycle")
        .default_val(1);
    RAMULATOR_PARSE_PARAM(m_drain_after_trace, bool, "drain_after_trace")
        .default_val(false);

    if (m_max_issue_per_cycle == 0) {
      throw std::runtime_error("PIMTrace: max_issue_per_cycle must be greater than zero");
    }
  }

  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    if (m_max_issue_per_cycle > 1) {
      const int num_channels = memory_system->get_num_channels();
      if (num_channels <= 0) {
        throw std::runtime_error("PIMTrace: memory system has no channels");
      }
      m_channel_traces.resize(num_channels);
      m_channel_indices.assign(num_channels, 0);
    }
    m_logger.info(fmt::format("Loading PIM trace {} ...", m_trace_path));
    load_trace(m_trace_path);
    m_logger.info(fmt::format("Loaded {} PIM trace entries.", m_trace_length));
  }

  void tick() override {
    if (m_max_issue_per_cycle > 1) {
      tick_parallel_channels();
      return;
    }

    if (m_drain_after_trace && m_issued >= m_trace_length) {
      return;
    }

    const TraceEntry& e = m_trace[m_curr_idx];
    Request req(e.addr, e.type_id);
    req.size_bytes = m_memory_system->get_tx_bytes();
    if (m_drain_after_trace) {
      req.callback = [this](Request&) { m_completed++; };
    }
    if (m_memory_system->send(req)) {
      m_curr_idx = (m_curr_idx + 1) % m_trace_length;
      m_issued++;
    }
  }

  bool is_finished() override {
    return m_drain_after_trace ? m_completed >= m_trace_length
                               : m_issued >= m_trace_length;
  }

 private:
  void tick_parallel_channels() {
    const size_t num_channels = m_channel_traces.size();
    size_t issued_this_cycle = 0;

    for (size_t offset = 0;
         offset < num_channels && issued_this_cycle < m_max_issue_per_cycle;
         offset++) {
      const size_t channel = (m_next_channel + offset) % num_channels;
      size_t& index = m_channel_indices[channel];
      if (index >= m_channel_traces[channel].size()) {
        continue;
      }

      const TraceEntry& e = m_channel_traces[channel][index];
      Request req(e.addr, e.type_id);
      req.size_bytes = m_memory_system->get_tx_bytes();
      if (m_drain_after_trace) {
        req.callback = [this](Request&) { m_completed++; };
      }
      if (m_memory_system->send(req)) {
        index++;
        m_issued++;
        issued_this_cycle++;
      }
    }

    m_next_channel = (m_next_channel + 1) % num_channels;
  }

  void load_trace(const std::string& path_str) {
    fs::path p(path_str);
    if (!fs::exists(p)) {
      throw std::runtime_error(fmt::format("PIMTrace: file not found: {}", path_str));
    }
    std::ifstream f(p);
    if (!f.is_open()) {
      throw std::runtime_error(fmt::format("PIMTrace: cannot open: {}", path_str));
    }

    std::string line;
    int line_num = 0;
    while (std::getline(f, line)) {
      line_num++;
      if (line.empty() || line[0] == '#') continue;

      std::vector<std::string> tokens;
      tokenize(tokens, line, " ");
      if (tokens.size() != 2) {
        throw std::runtime_error(fmt::format(
            "PIMTrace {}:{}: expected 2 tokens, got {}", path_str, line_num, tokens.size()));
      }

      int type_id = PIMRequestType::from_string(tokens[0]);
      if (type_id < 0) {
        throw std::runtime_error(fmt::format(
            "PIMTrace {}:{}: unknown op '{}'. Valid ops: "
            "R W MAC_AB MAC_SB MAC_PB "
            "WR_BB RD_BB WR_RB RD_RB MV_RB MV_BB SFM ACT_FUNC SET_MODEL SET_HEAD BARRIER",
            path_str, line_num, tokens[0]));
      }

      Addr_t addr = static_cast<Addr_t>(std::stoull(tokens[1], nullptr, 0));
      if (m_max_issue_per_cycle > 1) {
        const int channel = m_memory_system->get_channel_id(addr);
        if (channel < 0 || channel >= static_cast<int>(m_channel_traces.size())) {
          throw std::runtime_error(fmt::format(
              "PIMTrace {}:{}: address maps to invalid channel {}", path_str, line_num, channel));
        }
        m_channel_traces[channel].push_back({type_id, addr});
      } else {
        m_trace.push_back({type_id, addr});
      }
      m_trace_length++;
    }

    if (m_trace_length == 0) {
      throw std::runtime_error(fmt::format("PIMTrace: empty trace file: {}", path_str));
    }
  }
};

}
