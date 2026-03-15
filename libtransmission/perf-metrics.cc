// This file Copyright © Mnemosyne LLC.
// It may be used under GPLv2 (SPDX: GPL-2.0-only), GPLv3 (SPDX: GPL-3.0-only),
// or any future license endorsed by Mnemosyne LLC.
// License text can be found in the licenses/ folder.

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#ifndef _WIN32
#include <time.h>
#include <unistd.h>
#endif

#include <fmt/format.h>

#include "libtransmission/env.h"
#include "libtransmission/file-utils.h"
#include "libtransmission/perf-metrics.h"
#include "libtransmission/session.h"
#include "libtransmission/tr-assert.h"
#include "libtransmission/utils.h"

using namespace std::literals;

namespace
{
constexpr auto SchemaVersion = 1;
constexpr auto DefaultInterval = std::chrono::seconds{ 5 };

[[nodiscard]] bool parse_bool(std::string_view const value)
{
    return value == "1"sv || value == "true"sv || value == "yes"sv || value == "on"sv;
}

[[nodiscard]] auto make_key(tr_torrent_id_t const tor_id, uint32_t const item) noexcept
{
    return (uint64_t{ tor_id } << 32U) | item;
}

[[nodiscard]] double quantile_ms(std::vector<double>& samples, double q)
{
    if (std::empty(samples))
    {
        return 0.0;
    }

    std::ranges::sort(samples);
    auto const pos = static_cast<size_t>(std::clamp(q, 0.0, 1.0) * static_cast<double>(samples.size() - 1U));
    return samples[pos];
}

[[nodiscard]] std::string json_escape(std::string_view input)
{
    auto out = std::string{};
    out.reserve(input.size() + 8U);
    for (auto const ch : input)
    {
        switch (ch)
        {
        case '"':
            out += "\\\"";
            break;
        case '\\':
            out += "\\\\";
            break;
        case '\n':
            out += "\\n";
            break;
        case '\r':
            out += "\\r";
            break;
        case '\t':
            out += "\\t";
            break;
        default:
            out += ch;
            break;
        }
    }

    return out;
}

class PerfMetrics final : public tr_perf_metrics
{
public:
    explicit PerfMetrics(tr_session const& session)
        : output_path_{ tr_env_get_string(
              "TR_PERF_METRICS_OUTPUT_FILE",
              tr_pathbuf{ session.configDir(), "/perf-metrics.jsonl"sv }) }
        , scenario_id_{ tr_env_get_string("TR_PERF_METRICS_SCENARIO_ID", "default") }
        , run_id_{ tr_env_get_string("TR_PERF_METRICS_RUN_ID", "run-0") }
        , commit_sha_{ tr_env_get_string("TR_PERF_METRICS_COMMIT_SHA", "unknown") }
    {
        if (auto const raw_interval = tr_env_get_string("TR_PERF_METRICS_INTERVAL_SECONDS"); !std::empty(raw_interval))
        {
            if (auto const parsed = tr_parseNum<int64_t>(raw_interval); parsed && *parsed > 0)
            {
                emit_interval_ = std::chrono::seconds{ *parsed };
            }
        }

        output_.open(output_path_, std::ios::out | std::ios::app);
        is_open_ = output_.is_open();
    }

    void add_uploaded(uint32_t const n_bytes) override
    {
        uploaded_total_ += n_bytes;
    }

    void add_downloaded(uint32_t const n_bytes) override
    {
        downloaded_total_ += n_bytes;
    }

    void on_request_sent(tr_torrent_id_t const tor_id, tr_piece_index_t const piece, tr_block_span_t const span) override
    {
        auto const now = std::chrono::steady_clock::now();
        for (auto block = span.begin; block < span.end; ++block)
        {
            auto const block_key = make_key(tor_id, block);
            block_request_at_.try_emplace(block_key, now);

            auto const piece_key = make_key(tor_id, piece);
            piece_start_at_.try_emplace(piece_key, now);
        }
    }

    void on_block_received(tr_torrent_id_t const tor_id, tr_block_index_t const block) override
    {
        auto const now = std::chrono::steady_clock::now();
        auto const key = make_key(tor_id, block);
        if (auto const it = block_request_at_.find(key); it != std::end(block_request_at_))
        {
            auto const latency = std::chrono::duration<double, std::milli>(now - it->second).count();
            request_queue_latency_ms_.push_back(latency);
            block_request_at_.erase(it);
        }
    }

    void on_piece_completed(tr_torrent_id_t const tor_id, tr_piece_index_t const piece) override
    {
        auto const now = std::chrono::steady_clock::now();
        auto const key = make_key(tor_id, piece);
        if (auto const it = piece_start_at_.find(key); it != std::end(piece_start_at_))
        {
            auto const latency = std::chrono::duration<double, std::milli>(now - it->second).count();
            piece_completion_latency_ms_.push_back(latency);
            piece_start_at_.erase(it);
        }
    }

    void on_main_loop_tick(
        std::chrono::system_clock::time_point const now,
        std::chrono::steady_clock::time_point const now_steady) override
    {
        if (last_loop_tick_)
        {
            auto const period = now_steady - *last_loop_tick_;
            auto const jitter = std::abs(std::chrono::duration<double, std::milli>(period - 1s).count());
            loop_jitter_ms_.push_back(jitter);
        }
        last_loop_tick_ = now_steady;

        sample_process();

        if (!next_emit_at_)
        {
            next_emit_at_ = now + emit_interval_;
        }
        else if (now >= *next_emit_at_)
        {
            emit(now);
            next_emit_at_ = now + emit_interval_;
        }
    }

    void flush(std::chrono::system_clock::time_point const now) override
    {
        emit(now);
    }

private:
    void sample_process()
    {
#ifndef _WIN32
        // CPU
        auto cpu = ::timespec{};
        if (::clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &cpu) == 0)
        {
            auto const cpu_now = std::chrono::seconds{ cpu.tv_sec } + std::chrono::nanoseconds{ cpu.tv_nsec };
            auto const steady_now = std::chrono::steady_clock::now();
            if (last_cpu_time_ && last_cpu_steady_)
            {
                auto const wall_delta = std::chrono::duration<double>(steady_now - *last_cpu_steady_).count();
                if (wall_delta > 0.0)
                {
                    auto const cpu_delta = std::chrono::duration<double>(cpu_now - *last_cpu_time_).count();
                    auto const percent = std::max(0.0, 100.0 * cpu_delta / wall_delta);
                    cpu_sum_ += percent;
                    cpu_peak_ = std::max(cpu_peak_, percent);
                    ++cpu_samples_;
                }
            }

            last_cpu_time_ = cpu_now;
            last_cpu_steady_ = steady_now;
        }

        // RSS
        auto statm = std::ifstream{ "/proc/self/statm" };
        long pages = 0;
        long resident = 0;
        if (statm >> pages >> resident)
        {
            auto const page_size = static_cast<double>(::sysconf(_SC_PAGESIZE));
            auto const rss_bytes = resident * page_size;
            rss_sum_bytes_ += rss_bytes;
            rss_peak_bytes_ = std::max(rss_peak_bytes_, rss_bytes);
            ++rss_samples_;
        }
#endif
    }

    void emit(std::chrono::system_clock::time_point const now)
    {
        if (!is_open_)
        {
            return;
        }

        auto piece_samples = piece_completion_latency_ms_;
        auto req_samples = request_queue_latency_ms_;
        auto jitter_samples = loop_jitter_ms_;

        auto const piece_p50 = quantile_ms(piece_samples, 0.50);
        auto const piece_p95 = quantile_ms(piece_samples, 0.95);
        auto const piece_p99 = quantile_ms(piece_samples, 0.99);

        auto const req_p50 = quantile_ms(req_samples, 0.50);
        auto const req_p95 = quantile_ms(req_samples, 0.95);
        auto const req_p99 = quantile_ms(req_samples, 0.99);

        auto const jitter_p50 = quantile_ms(jitter_samples, 0.50);
        auto const jitter_p95 = quantile_ms(jitter_samples, 0.95);
        auto const jitter_p99 = quantile_ms(jitter_samples, 0.99);

        auto const dt = std::max(1e-9, std::chrono::duration<double>(now - last_emit_at_).count());
        auto const download_bps = static_cast<double>(downloaded_total_ - last_downloaded_total_) / dt;
        auto const upload_bps = static_cast<double>(uploaded_total_ - last_uploaded_total_) / dt;

        auto const cpu_avg = cpu_samples_ == 0U ? 0.0 : cpu_sum_ / static_cast<double>(cpu_samples_);
        auto const rss_avg = rss_samples_ == 0U ? 0.0 : rss_sum_bytes_ / static_cast<double>(rss_samples_);

        auto const ts = fmt::format("{:%FT%TZ}", fmt::gmtime(std::chrono::system_clock::to_time_t(now)));
        output_ << fmt::format(
            "{{\"schema_version\":{},\"timestamp\":\"{}\",\"labels\":{{\"scenario_id\":\"{}\",\"run_id\":\"{}\",\"commit_sha\":\"{}\"}},\"throughput\":{{\"download_bps\":{:.3f},\"upload_bps\":{:.3f}}},\"piece_completion_latency_ms\":{{\"p50\":{:.3f},\"p95\":{:.3f},\"p99\":{:.3f}}},\"request_queue_latency_ms\":{{\"p50\":{:.3f},\"p95\":{:.3f},\"p99\":{:.3f}}},\"main_loop_jitter_ms\":{{\"p50\":{:.3f},\"p95\":{:.3f},\"p99\":{:.3f}}},\"cpu_percent\":{{\"avg\":{:.3f},\"peak\":{:.3f}}},\"rss_bytes\":{{\"avg\":{:.3f},\"peak\":{:.3f}}}}}\n",
            SchemaVersion,
            ts,
            json_escape(scenario_id_),
            json_escape(run_id_),
            json_escape(commit_sha_),
            download_bps,
            upload_bps,
            piece_p50,
            piece_p95,
            piece_p99,
            req_p50,
            req_p95,
            req_p99,
            jitter_p50,
            jitter_p95,
            jitter_p99,
            cpu_avg,
            cpu_peak_,
            rss_avg,
            rss_peak_bytes_);
        output_.flush();

        last_emit_at_ = now;
        last_downloaded_total_ = downloaded_total_;
        last_uploaded_total_ = uploaded_total_;
        piece_completion_latency_ms_.clear();
        request_queue_latency_ms_.clear();
        loop_jitter_ms_.clear();
        cpu_sum_ = 0.0;
        cpu_peak_ = 0.0;
        cpu_samples_ = 0U;
        rss_sum_bytes_ = 0.0;
        rss_peak_bytes_ = 0.0;
        rss_samples_ = 0U;
    }

private:
    std::string output_path_;
    std::string scenario_id_;
    std::string run_id_;
    std::string commit_sha_;

    std::ofstream output_;
    bool is_open_ = false;

    uint64_t uploaded_total_ = 0;
    uint64_t downloaded_total_ = 0;
    uint64_t last_uploaded_total_ = 0;
    uint64_t last_downloaded_total_ = 0;

    std::unordered_map<uint64_t, std::chrono::steady_clock::time_point> block_request_at_;
    std::unordered_map<uint64_t, std::chrono::steady_clock::time_point> piece_start_at_;

    std::vector<double> piece_completion_latency_ms_;
    std::vector<double> request_queue_latency_ms_;
    std::vector<double> loop_jitter_ms_;

    std::chrono::seconds emit_interval_ = DefaultInterval;
    std::chrono::system_clock::time_point last_emit_at_ = std::chrono::system_clock::now();
    std::optional<std::chrono::system_clock::time_point> next_emit_at_;
    std::optional<std::chrono::steady_clock::time_point> last_loop_tick_;

    std::optional<std::chrono::nanoseconds> last_cpu_time_;
    std::optional<std::chrono::steady_clock::time_point> last_cpu_steady_;
    double cpu_sum_ = 0.0;
    double cpu_peak_ = 0.0;
    size_t cpu_samples_ = 0U;

    double rss_sum_bytes_ = 0.0;
    double rss_peak_bytes_ = 0.0;
    size_t rss_samples_ = 0U;
};

} // namespace

std::unique_ptr<tr_perf_metrics> tr_perf_metrics::maybe_create(tr_session const& session)
{
    if (!parse_bool(tr_env_get_string("TR_PERF_METRICS_ENABLED", "0")))
    {
        return nullptr;
    }

    return std::make_unique<PerfMetrics>(session);
}
