// This file Copyright © Mnemosyne LLC.
// It may be used under GPLv2 (SPDX: GPL-2.0-only), GPLv3 (SPDX: GPL-3.0-only),
// or any future license endorsed by Mnemosyne LLC.
// License text can be found in the licenses/ folder.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>
#include <cstdlib>
#include <new>

#define LIBTRANSMISSION_PEER_MODULE

#include <libtransmission/crypto-utils.h>
#include <libtransmission/peer-mgr-wishlist.h>
#include <libtransmission/peer-mgr.h>
#include <libtransmission/quark.h>
#include <libtransmission/tr-buffer.h>
#include <libtransmission/variant.h>

struct AllocStats
{
    std::atomic<uint64_t> allocs = 0;
    std::atomic<uint64_t> bytes = 0;
    std::atomic<bool> enabled = false;
};

auto& alloc_stats()
{
    static auto stats = AllocStats{};
    return stats;
}

thread_local bool g_alloc_guard = false;

void* operator_new_impl(size_t size)
{
    auto* p = std::malloc(size);
    if (p == nullptr)
    {
        throw std::bad_alloc{};
    }

    auto& stats = alloc_stats();
    if (stats.enabled.load(std::memory_order_relaxed) && !g_alloc_guard)
    {
        g_alloc_guard = true;
        stats.allocs.fetch_add(1U, std::memory_order_relaxed);
        stats.bytes.fetch_add(size, std::memory_order_relaxed);
        g_alloc_guard = false;
    }

    return p;
}

void operator delete(void* ptr) noexcept
{
    std::free(ptr);
}

void operator delete(void* ptr, std::size_t) noexcept
{
    std::free(ptr);
}

void* operator new(std::size_t size)
{
    return operator_new_impl(size);
}

void* operator new[](std::size_t size)
{
    return operator_new_impl(size);
}

void operator delete[](void* ptr) noexcept
{
    std::free(ptr);
}

void operator delete[](void* ptr, std::size_t) noexcept
{
    std::free(ptr);
}

namespace
{

struct Sample
{
    double ns_per_op = 0.0;
    double allocs_per_op = 0.0;
    double bytes_per_op = 0.0;
};

struct Result
{
    std::string name;
    double ns_mean = 0.0;
    double ns_stddev = 0.0;
    double allocs_mean = 0.0;
    double allocs_stddev = 0.0;
    double bytes_mean = 0.0;
    double bytes_stddev = 0.0;
};

class WishlistMediator final : public Wishlist::Mediator
{
public:
    std::map<tr_block_index_t, uint8_t> active_request_count_;
    std::map<tr_piece_index_t, tr_block_span_t> block_span_;
    std::map<tr_piece_index_t, tr_priority_t> piece_priority_;
    std::map<tr_piece_index_t, size_t> piece_replication_;
    std::set<tr_block_index_t> client_has_block_;
    std::set<tr_piece_index_t> client_has_piece_;
    std::set<tr_piece_index_t> client_wants_piece_;

    [[nodiscard]] bool client_has_block(tr_block_index_t block) const override
    {
        return client_has_block_.contains(block);
    }

    [[nodiscard]] bool client_has_piece(tr_piece_index_t piece) const override
    {
        return client_has_piece_.contains(piece);
    }

    [[nodiscard]] bool client_wants_piece(tr_piece_index_t piece) const override
    {
        return client_wants_piece_.contains(piece);
    }

    [[nodiscard]] bool is_sequential_download() const override
    {
        return false;
    }

    [[nodiscard]] tr_piece_index_t sequential_download_from_piece() const override
    {
        return 0;
    }

    [[nodiscard]] size_t count_piece_replication(tr_piece_index_t piece) const override
    {
        return piece_replication_.contains(piece) ? piece_replication_.at(piece) : 0U;
    }

    [[nodiscard]] tr_block_span_t block_span(tr_piece_index_t piece) const override
    {
        return block_span_.at(piece);
    }

    [[nodiscard]] tr_piece_index_t piece_count() const override
    {
        return static_cast<tr_piece_index_t>(std::size(block_span_));
    }

    [[nodiscard]] tr_priority_t priority(tr_piece_index_t piece) const override
    {
        return piece_priority_.contains(piece) ? piece_priority_.at(piece) : TR_PRI_NORMAL;
    }
};

uint64_t xorshift64(uint64_t& x)
{
    x ^= x << 13U;
    x ^= x >> 7U;
    x ^= x << 17U;
    return x;
}

std::vector<Sample> run_benchmark(std::function<void()> const& fn, size_t repeats, size_t iterations)
{
    auto samples = std::vector<Sample>{};
    samples.reserve(repeats);

    for (size_t r = 0; r < repeats; ++r)
    {
        auto& stats = alloc_stats();
        stats.allocs.store(0U, std::memory_order_relaxed);
        stats.bytes.store(0U, std::memory_order_relaxed);
        stats.enabled.store(true, std::memory_order_relaxed);

        auto const start = std::chrono::steady_clock::now();
        for (size_t i = 0; i < iterations; ++i)
        {
            fn();
        }
        auto const end = std::chrono::steady_clock::now();

        stats.enabled.store(false, std::memory_order_relaxed);

        auto const elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
        samples.emplace_back(
            Sample{
                .ns_per_op = static_cast<double>(elapsed_ns) / static_cast<double>(iterations),
                .allocs_per_op = static_cast<double>(stats.allocs.load(std::memory_order_relaxed)) /
                    static_cast<double>(iterations),
                .bytes_per_op = static_cast<double>(stats.bytes.load(std::memory_order_relaxed)) /
                    static_cast<double>(iterations),
            });
    }

    return samples;
}

double mean(std::vector<double> const& values)
{
    if (std::empty(values))
    {
        return 0.0;
    }

    auto const sum = std::accumulate(std::begin(values), std::end(values), 0.0);
    return sum / static_cast<double>(std::size(values));
}

double stddev(std::vector<double> const& values, double m)
{
    if (std::size(values) <= 1U)
    {
        return 0.0;
    }

    double acc = 0.0;
    for (auto const v : values)
    {
        auto const d = v - m;
        acc += d * d;
    }
    return std::sqrt(acc / static_cast<double>(std::size(values) - 1U));
}

Result summarize(std::string name, std::vector<Sample> const& samples)
{
    auto ns = std::vector<double>{};
    auto allocs = std::vector<double>{};
    auto bytes = std::vector<double>{};
    ns.reserve(std::size(samples));
    allocs.reserve(std::size(samples));
    bytes.reserve(std::size(samples));

    for (auto const& sample : samples)
    {
        ns.push_back(sample.ns_per_op);
        allocs.push_back(sample.allocs_per_op);
        bytes.push_back(sample.bytes_per_op);
    }

    auto const ns_mean = mean(ns);
    auto const allocs_mean = mean(allocs);
    auto const bytes_mean = mean(bytes);

    return Result{
        .name = std::move(name),
        .ns_mean = ns_mean,
        .ns_stddev = stddev(ns, ns_mean),
        .allocs_mean = allocs_mean,
        .allocs_stddev = stddev(allocs, allocs_mean),
        .bytes_mean = bytes_mean,
        .bytes_stddev = stddev(bytes, bytes_mean),
    };
}

void write_summary(
    std::string const& output,
    std::string const& commit,
    size_t repeats,
    size_t iterations,
    std::vector<Result> const& results)
{
    auto out = std::ostringstream{};
    out << "{\n";
    out << "  \"commit\": \"" << commit << "\",\n";
    out << "  \"repeats\": " << repeats << ",\n";
    out << "  \"iterations\": " << iterations << ",\n";
    out << "  \"benchmarks\": [\n";

    for (size_t i = 0; i < std::size(results); ++i)
    {
        auto const& result = results[i];
        out << "    {\n";
        out << "      \"name\": \"" << result.name << "\",\n";
        out << "      \"ns_per_op\": { \"mean\": " << std::fixed << std::setprecision(4) << result.ns_mean
            << ", \"stddev\": " << result.ns_stddev << " },\n";
        out << "      \"allocations_per_op\": { \"mean\": " << result.allocs_mean << ", \"stddev\": " << result.allocs_stddev
            << " },\n";
        out << "      \"bytes_per_op\": { \"mean\": " << result.bytes_mean << ", \"stddev\": " << result.bytes_stddev << " }\n";
        out << "    }" << (i + 1U < std::size(results) ? "," : "") << "\n";
    }

    out << "  ]\n";
    out << "}\n";

    if (output == "-")
    {
        std::cout << out.str();
        return;
    }

    auto file = std::ofstream{ output };
    file << out.str();
}

} // namespace

int main(int argc, char** argv)
{
    std::string output = "microbench-summary.json";
    std::string commit = "unknown";
    size_t repeats = 12U;
    size_t iterations = 800U;

    for (int i = 1; i < argc; ++i)
    {
        auto const arg = std::string_view{ argv[i] };
        if (arg == "--output" && i + 1 < argc)
        {
            output = argv[++i];
        }
        else if (arg == "--commit" && i + 1 < argc)
        {
            commit = argv[++i];
        }
        else if (arg == "--repeats" && i + 1 < argc)
        {
            repeats = static_cast<size_t>(std::stoul(argv[++i]));
        }
        else if (arg == "--iterations" && i + 1 < argc)
        {
            iterations = static_cast<size_t>(std::stoul(argv[++i]));
        }
    }

    auto results = std::vector<Result>{};

    // piece picker hot path
    auto mediator = WishlistMediator{};
    auto block = tr_block_index_t{ 0 };
    for (tr_piece_index_t piece = 0; piece < 4096; ++piece)
    {
        mediator.block_span_[piece] = { .begin = block, .end = block + 16 };
        mediator.client_wants_piece_.insert(piece);
        mediator.piece_priority_[piece] = (piece % 13 == 0) ? TR_PRI_HIGH : TR_PRI_NORMAL;
        mediator.piece_replication_[piece] = 1U + (piece % 32U);
        block += 16;
    }
    auto wishlist = Wishlist{ mediator };
    auto peer_seed = uint64_t{ 0xC0FFEE1234ULL };
    auto piece_picker_samples = run_benchmark(
        [&wishlist, &peer_seed]()
        {
            auto const peer_mask = xorshift64(peer_seed);
            auto spans = wishlist.next(64, [peer_mask](tr_piece_index_t piece) { return ((piece + peer_mask) % 3U) != 0U; });
            size_t volatile sink = std::size(spans);
            (void)sink;
        },
        repeats,
        iterations);
    results.emplace_back(summarize("piece_picker.wishlist_next", piece_picker_samples));

    // peer selection path: compact peer decoding
    auto compact = std::vector<std::byte>{};
    auto flags = std::vector<uint8_t>{};
    compact.reserve(6U * 512U);
    flags.reserve(512U);
    for (uint32_t i = 0; i < 512U; ++i)
    {
        compact.push_back(static_cast<std::byte>(10U));
        compact.push_back(static_cast<std::byte>((i / 256U) % 255U));
        compact.push_back(static_cast<std::byte>((i / 16U) % 255U));
        compact.push_back(static_cast<std::byte>(i % 255U));
        auto const port = static_cast<uint16_t>(20000U + i);
        compact.push_back(static_cast<std::byte>((port >> 8U) & 0xffU));
        compact.push_back(static_cast<std::byte>(port & 0xffU));
        flags.push_back(static_cast<uint8_t>(i % 8U));
    }
    auto peer_samples = run_benchmark(
        [&compact, &flags]()
        {
            auto pex = tr_pex::from_compact_ipv4(std::data(compact), std::size(compact), std::data(flags), std::size(flags));
            bool volatile sink = pex.front().is_valid_for_peers(TR_PEER_FROM_PEX);
            (void)sink;
        },
        repeats,
        iterations);
    results.emplace_back(summarize("peer_selection.from_compact_ipv4", peer_samples));

    // buffer management path
    auto buffer_samples = run_benchmark(
        []()
        {
            auto buf = tr::StackBuffer<1024U>{};
            for (uint32_t i = 0; i < 256U; ++i)
            {
                buf.add_uint32(0xDEADBEEFU ^ i);
            }

            uint64_t sum = 0;
            while (!buf.empty())
            {
                sum += buf.to_uint32();
            }

            uint64_t volatile sink = sum;
            (void)sink;
        },
        repeats,
        iterations);
    results.emplace_back(summarize("buffers.stackbuffer_rw", buffer_samples));

    // crypto hot path
    auto payload = std::array<char, 16U * 1024U>{};
    for (size_t i = 0; i < std::size(payload); ++i)
    {
        payload[i] = static_cast<char>(i % 251U);
    }
    auto crypto_samples = run_benchmark(
        [&payload]()
        {
            auto digest = tr_sha1::digest(payload);
            auto volatile sink = digest[0];
            (void)sink;
        },
        repeats,
        iterations);
    results.emplace_back(summarize("crypto.sha1_16k", crypto_samples));

    // frequent RPC path: JSON parse + method lookup
    auto const request_json = std::string{
        R"({\"method\":\"torrent-get\",\"arguments\":{\"fields\":[\"id\",\"name\",\"status\"],\"ids\":[1,2,3,4,5],\"format\":\"objects\"},\"tag\":17})"
    };
    auto rpc_samples = run_benchmark(
        [&request_json]()
        {
            auto parsed = tr_variant_serde::json().parse(request_json);
            if (!parsed)
            {
                std::abort();
            }

            auto const* map = parsed->get_if<tr_variant::Map>();
            if (map == nullptr)
            {
                std::abort();
            }

            auto method = map->value_if<std::string_view>(TR_KEY_method).value_or(std::string_view{});
            auto volatile sink = std::size(method);
            (void)sink;
        },
        repeats,
        iterations);
    results.emplace_back(summarize("rpc.json_parse_method_lookup", rpc_samples));

    write_summary(output, commit, repeats, iterations, results);
    return 0;
}
