3340:         """)
3341:     html_parts.append("</div>")
3342:     return "".join(html_parts)
3343: 
3344: 
3345: def _select_mirror_strategically(
3346:     file_info: dict, mirrors: dict, thumb_mirrors: dict, is_ru: bool
3347: ) -> tuple[str, str]:
3348:     """
3349:     Выбирает URL для файла и его превью на основе приоритетов региона.
3350:     """
3351:     base_original_url = file_info.get("original_url", "")
3352:     base_thumbnail_url = file_info.get("thumbnail_url", "")
3353: 
3354:     # Проверка R2 CDN
3355:     r2_candidate = mirrors.get("r2") or mirrors.get("r2_url")
3356:     hf_candidate = mirrors.get("huggingface")
3357:     hf_valid = is_hf_link_allowed(hf_candidate, VALID_HF_REPOS)
3358:     zeroxzero_candidate = mirrors.get("0x0")
3359: 
3360:     # --- ВЫБОР ОРИГИНАЛА ---
3361:     if r2_candidate:
3362:         selected_original = r2_candidate
3363:     elif not is_ru:
3364:         if hf_valid:
3365:             selected_original = hf_candidate
3366:         elif zeroxzero_candidate:
3367:             selected_original = zeroxzero_candidate
3368:         elif mirrors.get("catbox"):
3369:             selected_original = mirrors["catbox"]
3370:         else:
3371:             selected_original = base_original_url
3372:     else:
3373:         # Для RU-IP: Приоритет HF или Telegram
3374:         if hf_valid:
3375:             selected_original = hf_candidate
3376:         elif zeroxzero_candidate:
3377:             selected_original = zeroxzero_candidate
3378:         else:
3379:             selected_original = base_original_url
3380: 
3381:     # --- ВЫБОР ПРЕВЬЮ (Thumbnail) ---
3382:     r2_thumb = thumb_mirrors.get("r2") or thumb_mirrors.get("r2_url")
3383:     if r2_thumb:
3384:         selected_thumbnail = r2_thumb
3385:     elif "telegraph" in thumb_mirrors:
3386:         selected_thumbnail = thumb_mirrors["telegraph"]
3387:     else:
3388:         hf_thumb = thumb_mirrors.get("huggingface")
3389:         hf_thumb_valid = is_hf_link_allowed(hf_thumb, VALID_HF_REPOS)
3390:         zeroxzero_thumb = thumb_mirrors.get("0x0")
3391: 
3392:         if not is_ru:
3393:             if "catbox" in thumb_mirrors:
3394:                 selected_thumbnail = thumb_mirrors["catbox"]
3395:             elif hf_thumb_valid:
3396:                 selected_thumbnail = hf_thumb
3397:             elif zeroxzero_thumb:
3398:                 selected_thumbnail = zeroxzero_thumb
3399:             else:
3400:                 selected_thumbnail = base_thumbnail_url
3401:         else:
3402:             if hf_thumb_valid:
3403:                 selected_thumbnail = hf_thumb
3404:             elif zeroxzero_thumb:
3405:                 selected_thumbnail = zeroxzero_thumb
3406:             else:
3407:                 selected_thumbnail = base_thumbnail_url
3408: 
3409:     return selected_original, selected_thumbnail
3410: 
3411: 
3412: async def enrich_extra_data(posts: List[dict], is_ru: bool = True):
3413:     if not posts:
3414:         return
3415:     all_fids = []
3416:     poll_post_ids = []
3417:     all_post_ids = []
3418: 
3419:     for p in posts:
3420:         all_post_ids.append(p["id"])
3421:         files = p.get("content", {}).get("files", [])
3422:         for f in files:
3423:             fid = f.get("original_file_id")
3424:             if fid:
3425:                 all_fids.append(fid)
3426:             tid = f.get("thumbnail_file_id")
3427:             if tid:
3428:                 all_fids.append(tid)
3429: 
3430:         if p.get("latest_replies"):
3431:             for r in p["latest_replies"]:
3432:                 all_post_ids.append(r["id"])
3433:                 r_files = r.get("content", {}).get("files", [])
3434:                 for rf in r_files:
3435:                     rfid = rf.get("original_file_id")
3436:                     if rfid:
3437:                         all_fids.append(rfid)
3438:                     rtid = rf.get("thumbnail_file_id")
3439:                     if rtid:
3440:                         all_fids.append(rtid)
3441: 
3442:         if "poll_data" in p.get("content", {}):
3443:             poll_post_ids.append(p["id"])
3444: 
3445:         if p.get("latest_replies"):
3446:             for r in p["latest_replies"]:
3447:                 if "poll_data" in r.get("content", {}):
3448:                     poll_post_ids.append(r["id"])
3449: 
3450:     dupe_map, blur_map, mirror_map = {}, {}, {}
3451:     failed_set = set()
3452:     backlinks_map = defaultdict(list)
3453:     tasks = []
3454: 
3455:     if all_fids:
3456:         from common.database import get_mirrors_batch, get_failed_files_batch
3457: 
3458:         tasks.append(get_duplicate_counts(all_fids))
3459:         tasks.append(get_blurhashes_batch(all_fids))
3460:         tasks.append(get_mirrors_batch(all_fids))
3461:         tasks.append(get_failed_files_batch(all_fids))
3462: 
3463:     if poll_post_ids:
3464:         for pid in poll_post_ids:
3465:             tasks.append(get_poll_results(pid))
3466: 
3467:     results = await asyncio.gather(*tasks, return_exceptions=True)
3468: 
3469:     res_idx = 0
3470:     if all_fids:
3471:         dupe_map = (
3472:             results[res_idx] if not isinstance(results[res_idx], Exception) else {}
3473:         )
3474:         res_idx += 1
3475:         blur_map = (
3476:             results[res_idx] if not isinstance(results[res_idx], Exception) else {}
3477:         )
3478:         res_idx += 1
3479:         mirror_map = (
3480:             results[res_idx] if not isinstance(results[res_idx], Exception) else {}
3481:         )
3482:         res_idx += 1
3483:         failed_set = (
3484:             results[res_idx]
3485:             if not isinstance(results[res_idx], Exception)
3486:             and isinstance(results[res_idx], (set, list, tuple))
3487:             else set()
3488:         )
3489:         res_idx += 1
3490: 
3491:     poll_results_map = {}
3492:     if poll_post_ids:
3493:         for i, pid in enumerate(poll_post_ids):
3494:             val = results[res_idx + i]
3495:             if not isinstance(val, Exception):
3496:                 poll_results_map[pid] = val
3497: 
3498:     if all_post_ids:
3499:         try:
3500:             db = await get_pool()
3501:             placeholders = ",".join("?" for _ in all_post_ids)
3502:             query = f"SELECT target_post_num, source_post_num FROM Backlinks WHERE target_post_num IN ({placeholders})"
3503:             async with db.execute(query, all_post_ids) as cursor:
3504:                 async for row in cursor:
3505:                     target, source = row
3506:                     backlinks_map[target].append(source)
3507:         except Exception as e:
3508:             print(f"Backlinks fetch error: {e}")
3509: 
3510:     for p in posts:
3511:         db_bl = backlinks_map.get(p["id"], [])
3512:         mem_bl = p.get("backlinks", [])
3513:         p["backlinks"] = sorted(list(set(mem_bl) | set(db_bl)))
3514: 
3515:         def update_files(file_list):
3516:             for f in file_list:
3517:                 fid = f.get("original_file_id")
3518:                 if not fid:
3519:                     continue
3520:                 f["blurhash"] = blur_map.get(fid)
3521:                 f["dupe_count"] = dupe_map.get(fid, 0)
3522: 
3523:                 tid = f.get("thumbnail_file_id")
3524:                 is_orig_failed = (
3525:                     (fid in failed_set)
3526:                     or f.get("is_broken")
3527:                     or (f.get("tags") in ("download_failed", "error"))
3528:                 )
3529:                 is_thumb_failed = (tid in failed_set) if tid else False
3530: 
3531:                 if is_orig_failed:
3532:                     f["is_broken"] = True
3533:                     f["download_failed"] = True
3534:                     f["original_url"] = ""
3535:                     f["thumbnail_url"] = ""
3536:                 else:
3537:                     mirrors = mirror_map.get(fid, {})
3538:                     thumb_mirrors = mirror_map.get(tid, {}) if tid else {}
3539:                     sel_orig, sel_thumb = _select_mirror_strategically(
3540:                         f, mirrors, thumb_mirrors, is_ru
3541:                     )
3542:                     f["original_url"] = sel_orig
3543:                     f["thumbnail_url"] = "" if is_thumb_failed else sel_thumb
3544:                     if is_thumb_failed:
3545:                         f["thumbnail_download_failed"] = True
3546: 
3547:         if p.get("content", {}).get("files"):
3548:             update_files(p["content"]["files"])
3549:         if p.get("latest_replies"):
3550:             for r in p["latest_replies"]:
3551:                 r_db_bl = backlinks_map.get(r["id"], [])
3552:                 r_mem_bl = r.get("backlinks", [])
3553:                 r["backlinks"] = sorted(list(set(r_mem_bl) | set(r_db_bl)))
3554:                 if r.get("content", {}).get("files"):
3555:                     update_files(r["content"]["files"])
3556: 
3557:         def apply_votes(post_obj):
3558:             if "poll_data" in post_obj.get("content", {}):
3559:                 real_votes = poll_results_map.get(post_obj["id"], {})
3560:                 frontend_votes = {}
3561:                 if real_votes:
3562:                     for opt_idx, count in real_votes.items():
3563:                         frontend_votes[str(opt_idx)] = [0] * count
3564:                 post_obj["content"]["poll_data"]["votes"] = frontend_votes
3565: 
3566:         apply_votes(p)
3567:         if p.get("latest_replies"):
3568:             for r in p["latest_replies"]:
3569:                 apply_votes(r)
3570: 
3571: 
3572: def _process_media_group(content: dict) -> None:
3573:     file_list = []
3574:     found_caption = None
3575:     for item in content.get("media", []):
3576:         f_type = item.get("type")
3577:         f_id = item.get("file_id") or item.get("media")
3578:         if not found_caption and item.get("caption"):
3579:             found_caption = item.get("caption")
3580:         if f_id and isinstance(f_id, str) and not f_id.startswith("<"):
3581:             clean_type = "image" if f_type == "photo" else f_type
3582:             file_list.append(
3583:                 {
3584:                     "type": clean_type,
3585:                     "original_file_id": f_id,
3586:                     "thumbnail_file_id": f_id,
3587:                     "filename": (
3588:                         f"media_{f_id[:8]}.jpg"
3589:                         if clean_type == "image"
3590:                         else f"media_{f_id[:8]}.mp4"
3591:                     ),
3592:                 }
3593:             )
3594:     content["files"] = file_list
3595:     if not content.get("text") and found_caption:
3596:         content["text"] = found_caption
3597: 
3598: 
3599: def _process_single_media(content: dict) -> None:
3600:     file_info = {"type": content["type"]}
3601:     ctype = content["type"]
3602:     if ctype == "photo" and content.get("photo") and isinstance(content["photo"], list):
3603:         try:
3604:             file_info["original_file_id"] = content["photo"][-1].get("file_id")
3605:             file_info["thumbnail_file_id"] = content["photo"][0].get("file_id")
3606:             file_info["type"] = "image"
3607:         except Exception:
3608:             pass
3609:     else:
3610:         f_obj = content.get(ctype) or content
3611:         f_id = f_obj.get("file_id")
3612:         thumb_source = f_obj.get("thumb") or f_obj.get("thumbnail")
3613:         if thumb_source and isinstance(thumb_source, dict):
3614:             file_info["thumbnail_file_id"] = thumb_source.get("file_id")
3615:         mime = f_obj.get("mime_type", "")
3616:         if ctype == "document" and mime.startswith("video/"):
3617:             file_info["type"] = "video"
3618:         if f_id:
3619:             file_info["original_file_id"] = f_id
3620:     if file_info.get("original_file_id"):
3621:         content["files"] = [file_info]
3622: 
3623: 
3624: def _process_files_list(content: dict) -> None:
3625:     from urllib.parse import quote
3626:     import time
3627: 
3628:     valid_files = []
3629:     for file_info in content["files"]:
3630:         file_info.setdefault("dupe_count", 0)
3631:         orig_url = file_info.get("original_url", "")
3632:         if orig_url and "local_file://" in orig_url:
3633:             clean_id = orig_url.split("local_file://")[1]
3634:             file_info["original_file_id"] = clean_id
3635:             file_info["original_url"] = f"/files/{clean_id}"
3636:         oid = file_info.get("original_file_id")
3637:         if not oid or oid.startswith("<"):
3638:             continue
3639:         fname = file_info.get("filename", "").lower()
3640:         if fname.endswith((".mp4", ".webm", ".mov", ".mkv")) and file_info.get(
3641:             "type"
3642:         ) not in ["voice", "audio"]:
3643:             file_info["type"] = "video"
3644:         if fname.endswith(".webm") and file_info.get("type") == "sticker":
3645:             file_info["type"] = "video"
3646:         ftype = file_info.get("type", "file")
3647:         ext_map = {
3648:             "video": "mp4",
3649:             "photo": "jpg",
3650:             "image": "jpg",
3651:             "audio": "mp3",
3652:             "voice": "ogg",
3653:             "sticker": "webp",
3654:             "video_note": "mp4",
3655:             "animation": "mp4",
3656:             "gif": "mp4",
3657:         }
3658: 
3659:         if not fname or fname.startswith(".") or fname == "file" or "." not in fname:
3660:             ext = ext_map.get(ftype, "dat")
3661:             prefix = (
3662:                 "vid"
3663:                 if ftype in ["video", "animation", "video_note", "gif"]
3664:                 else ("aud" if ftype in ["audio", "voice"] else "img")
3665:             )
3666:             short_id = oid[:8] if oid else str(int(time.time()))
3667:             file_info["filename"] = f"{prefix}_{short_id}.{ext}"
3668:         elif "." not in fname and ftype in ext_map:
3669:             file_info["filename"] = f"{fname}.{ext_map[ftype]}"
3670: 
3671:         safe_name = quote(str(file_info.get("filename", "file")).strip("/"))
3672: 
3673:         oid_str = str(oid) if oid else ""
3674:         if file_info.get("is_broken") or file_info.get("download_failed"):
3675:             file_info["is_broken"] = True
3676:             file_info["original_url"] = ""
3677:             file_info["thumbnail_url"] = ""
3678:         else:
3679:             if oid_str.startswith(("http://", "https://")):
3680:                 file_info["original_url"] = oid_str
3681:             else:
3682:                 clean_oid = oid_str.strip("/")
3683:                 if clean_oid:
3684:                     file_info["original_url"] = f"/files/{clean_oid}/{safe_name}"
3685:                 else:
3686:                     file_info["original_url"] = f"/files/{safe_name}"
3687: 
3688:             tid = file_info.get("thumbnail_file_id")
3689:             if tid:
3690:                 tid_str = str(tid)
3691:                 if tid_str.startswith(("http://", "https://")):
3692:                     file_info["thumbnail_url"] = tid_str
3693:                 else:
3694:                     file_info["thumbnail_url"] = f"/files/{tid_str.strip('/')}"
3695:             else:
3696:                 file_info["thumbnail_url"] = ""
3697:         valid_files.append(file_info)
3698:     content["files"] = valid_files
3699: 
3700: 
