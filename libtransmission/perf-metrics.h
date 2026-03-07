// This file Copyright © Mnemosyne LLC.
// It may be used under GPLv2 (SPDX: GPL-2.0-only), GPLv3 (SPDX: GPL-3.0-only),
// or any future license endorsed by Mnemosyne LLC.
// License text can be found in the licenses/ folder.

#pragma once

#include <chrono>
#include <cstdint>
#include <memory>
#include <string>

#include "libtransmission/types.h"

class tr_session;

class tr_perf_metrics
{
public:
    static std::unique_ptr<tr_perf_metrics> maybe_create(tr_session const& session);

    virtual ~tr_perf_metrics() = default;

    virtual void add_uploaded(uint32_t n_bytes) = 0;
    virtual void add_downloaded(uint32_t n_bytes) = 0;
    virtual void on_request_sent(tr_torrent_id_t tor_id, tr_piece_index_t piece, tr_block_span_t span) = 0;
    virtual void on_block_received(tr_torrent_id_t tor_id, tr_block_index_t block) = 0;
    virtual void on_piece_completed(tr_torrent_id_t tor_id, tr_piece_index_t piece) = 0;
    virtual void on_main_loop_tick(std::chrono::system_clock::time_point now, std::chrono::steady_clock::time_point now_steady) = 0;
    virtual void flush(std::chrono::system_clock::time_point now) = 0;
};
