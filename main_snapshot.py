  1769	def _collect_runtime_snapshot() -> dict:
  1770
  1771	    queue_sizes = {board: message_queues[board].qsize() for board in BOARDS if board in message_queues}
  1772	    top_queues = sorted(queue_sizes.items(), key=lambda item: item[1], reverse=True)[:5]
  1773	    queue_age_summary = _summarize_live_queue_ages(queue_sizes)
  1774	    priority_counts = {board: _safe_len(weekly_active_users.get(board, set())) for board in BOARDS}
  1775	    pending_done = 0
  1776	    try:
  1777	        pending_done = sum(1 for task in pending_edit_tasks.values() if task.done())
  1778	    except Exception:
  1779	        pending_done = -1
  1780	    board_totals = {
  1781	        "active_users": 0,
  1782	        "shadow_mutes": 0,
  1783	        "regular_mutes": 0,
  1784	        "threads": 0,
  1785	        "user_state": 0,
  1786	        "last_activity": 0,
  1787	        "reaction_queue_items": 0,
  1788	    }
  1789	    for board_id in BOARDS:
  1790	        b_data = board_data.get(board_id, {})
  1791	        users = b_data.get("users", {})
  1792	        board_totals["active_users"] += _safe_len(users.get("active", []))
  1793	        board_totals["shadow_mutes"] += _safe_len(b_data.get("shadow_mutes", {}))
  1794	        board_totals["regular_mutes"] += _safe_len(b_data.get("mutes", {}))
  1795	        board_totals["threads"] += _safe_len(b_data.get("threads_data", {}))
  1796	        board_totals["user_state"] += _safe_len(b_data.get("user_state", {}))
  1797	        board_totals["last_activity"] += _safe_len(b_data.get("last_activity", {}))
  1798	        reaction_queue = b_data.get("reaction_queue", {})
  1799	        if isinstance(reaction_queue, dict):
  1800	            board_totals["reaction_queue_items"] += sum(_safe_len(q) for q in reaction_queue.values())
  1801	    board_map_totals = _collect_board_map_totals()
  1802	    recipient_counts = _recipient_counts_snapshot()
  1803	    try:
  1804	        all_tasks = asyncio.all_tasks()
  1805	        task_stats = {
  1806	            "total": len(all_tasks),
  1807	            "done": sum(1 for task in all_tasks if task.done()),
  1808	        }
  1809	    except RuntimeError:
  1810	        task_stats = {"total": 0, "done": 0}
  1811	    return {
  1812	        "utc": datetime.now(UTC).isoformat(),
  1813	        "post_counter": state.get("post_counter", 0),
  1814	        "memory": _get_process_memory_snapshot(),
  1815	        "db_files": _get_db_file_snapshot(),
  1816	        "controlled_stop": _controlled_stop_snapshot(),
  1817	        "queues": {
  1818	            "total": sum(queue_sizes.values()),
  1819	            "by_board": queue_sizes,
  1820	            "top": top_queues,
  1821	            "age_by_board": queue_age_summary["by_board"],
  1822	            "oldest": queue_age_summary["oldest"],
  1823	            "in_flight": queue_age_summary["in_flight"],
  1824	        },
  1825	        "delivery_priority": {
  1826	            "enabled": PRIORITY_DELIVERY_ENABLED,
  1827	            "split_fanout": PRIORITY_SPLIT_FANOUT_ENABLED,
  1828	            "split_min_passive": PRIORITY_SPLIT_MIN_PASSIVE,
  1829	            "passive_slice_size": PRIORITY_PASSIVE_SLICE_SIZE,
  1830	            "passive_media_slice_size": PRIORITY_PASSIVE_MEDIA_SLICE_SIZE,
  1831	            "pressure_slice_age_sec": PRIORITY_PRESSURE_SLICE_AGE_SEC,
  1832	            "pressure_passive_slice_size": PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE,
  1833	            "pressure_passive_media_slice_size": PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE,
  1834	            "passive_max_preemptions": PASSIVE_MAX_PREEMPTIONS,
  1835	            "priority_phase_budget_sec": PRIORITY_PHASE_BUDGET_SEC,
  1836	            "passive_phase_budget_sec": PASSIVE_PHASE_BUDGET_SEC,
  1837	        "delivery_initial_chunk_size": DELIVERY_INITIAL_CHUNK_SIZE,
  1838	        "delivery_min_chunk_size": DELIVERY_MIN_CHUNK_SIZE,
  1839	        "delivery_per_recipient_timeout_sec": DELIVERY_PER_RECIPIENT_TIMEOUT_SEC,
  1840	        "delivery_telegram_request_timeout_sec": DELIVERY_TELEGRAM_REQUEST_TIMEOUT_SEC,
  1841	        "delivery_max_recipient_retries": DELIVERY_MAX_RECIPIENT_RETRIES,
  1842	        "delivery_phase_guard_sec": DELIVERY_PHASE_GUARD_SEC,
  1843	            "days": WEEKLY_ACTIVE_DAYS,
  1844	            "refresh_sec": WEEKLY_ACTIVE_REFRESH_SECONDS,
  1845	            "total_weekly_active": sum(priority_counts.values()),
  1846	            "by_board": priority_counts,
  1847	            "updated_at": weekly_active_updated_at.copy(),
  1848	        },
  1849	        "recipients": recipient_counts,
  1850	        "durable_delivery": {
  1851	            "enabled": DURABLE_DELIVERY_QUEUE_ENABLED,
  1852	            **durable_delivery_stats,
  1853	        },
  1854	        "anime_media": {
  1855	            "concurrency": ANIME_MEDIA_CONCURRENCY,
  1856	            "b_max_stacked_images": B_MAX_STACKED_ANIME_IMAGES,
  1857	            "url_timeout_sec": ANIME_URL_FETCH_TIMEOUT_SEC,
  1858	            "url_total_sec": ANIME_URL_FETCH_TOTAL_SEC,
  1859	            "url_parallel": ANIME_URL_FETCH_PARALLEL,
  1860	            "download_timeout_sec": ANIME_DOWNLOAD_TIMEOUT_SEC,
  1861	            "download_total_sec": ANIME_DOWNLOAD_TOTAL_SEC,
  1862	            "download_parallel": ANIME_DOWNLOAD_PARALLEL,
  1863	            "refill_rounds": ANIME_REFILL_ROUNDS,
  1864	        },
  1865	        "mode_punchup": {
  1866	            "enabled": MODE_PUNCHUP_ENABLED,
  1867	            "runtime_enabled": mode_punchup_runtime_enabled,
  1868	            "queue_shed_sec": MODE_PUNCHUP_QUEUE_SHED_SEC,
  1869	            "slow_log_us": MODE_PUNCHUP_SLOW_LOG_US,
  1870	            "stats": _summarize_mode_punchup_stats(),
  1871	        },
  1872	        "contextual_replies": {
  1873	            "enabled": CONTEXTUAL_REPLIES_ENABLED,
  1874	            "cooldown_sec": CONTEXTUAL_REPLY_COOLDOWN_SEC,
  1875	            "daily_limit": CONTEXTUAL_REPLY_DAILY_LIMIT,
  1876	            "groups_ru": _safe_len(CONTEXTUAL_REPLIES),
  1877	            "tracked_users": _safe_len(contextual_reply_tracker),
  1878	            "stats": dict(contextual_reply_stats),
  1879	        },
  1880	        "reply_coverage": {
  1881	            "updated_at": reply_coverage_updated_at,
  1882	            **reply_coverage_stats,
  1883	        },
  1884	        "delivery": _summarize_delivery_metrics(),
  1885	        "maps": {
  1886	            "messages_storage": _safe_len(messages_storage),
  1887	            "post_to_messages": _safe_len(post_to_messages),
  1888	            "message_to_post": _safe_len(message_to_post),
  1889	            "shadow_fake_post_counters": _safe_len(shadow_fake_post_counters),
  1890	            "pending_edit_tasks": _safe_len(pending_edit_tasks),
  1891	            "pending_edit_done": pending_done,
  1892	            "current_media_groups": _safe_len(current_media_groups),
  1893	            "media_group_timers": _safe_len(media_group_timers),
  1894	            "posts_pending_deletion": _safe_len(posts_pending_deletion),
  1895	            "unknown_command_tracker": _safe_len(unknown_command_tracker),
  1896	            "contextual_reply_tracker": _safe_len(contextual_reply_tracker),
  1897	            "user_spam_locks": _safe_len(user_spam_locks),
  1898	            "generate_locks": _safe_len(generate_locks),
  1899	            "user_last_thread_action": _safe_len(user_last_thread_action),
  1900	            "reaction_ratelimit": _safe_len(reaction_ratelimit),
  1901	            "last_poll_creation_time": _safe_len(last_poll_creation_time),
  1902	            "last_poll_vote_time": _safe_len(last_poll_vote_time),
  1903	            "user_hourly_image_count": _safe_len(user_hourly_image_count),
  1904	            "user_hourly_image_reset": _safe_len(user_hourly_image_reset),
  1905	            "author_reaction_notify_tracker": _safe_len(author_reaction_notify_tracker),
  1906	            "network_retry_state": _safe_len(network_retry_state),
  1907	            "image_spam_tracker": _safe_len(image_spam_tracker),
  1908	            "stream_cache": _safe_len(stream_cache),
  1909	            "graph_stats": _safe_len(graph_stats),
  1910	            "roulette_events": _safe_len(ROULETTE_EVENTS),
  1911	        },
  1912	        "board_maps": board_map_totals,
  1913	        "board_totals": board_totals,
  1914	        "asyncio_tasks": task_stats,
  1915	        "gc_count": gc.get_count(),
  1916	        "tracemalloc": {
  1917	            "enabled": tracemalloc.is_tracing(),
  1918	            "current_mb": round(tracemalloc.get_traced_memory()[0] / 1024 / 1024, 2) if tracemalloc.is_tracing() else 0.0,
  1919	            "peak_mb": round(tracemalloc.get_traced_memory()[1] / 1024 / 1024, 2) if tracemalloc.is_tracing() else 0.0,
  1920	        },
  1921	    }
