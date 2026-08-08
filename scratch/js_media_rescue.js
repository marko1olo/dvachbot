11240:         let thumbHtml = '';
11241:         const files = data.content.files || [];
11242:         if (files.length > 0) {
11243:             const f = files[0];
11244:             const isVid = ['video', 'gif', 'animation', 'video_note'].includes(f.type);
11245:             const mediaUrl = f.original_url || (f.original_file_id ? `/files/${f.original_file_id}` : "");
11246:             const thumbUrl = f.thumbnail_url || (f.thumbnail_file_id ? `/files/${f.thumbnail_file_id}` : "");
11247:             
11248:             if (typeof FailedMediaCache !== 'undefined' && ((mediaUrl && FailedMediaCache.isFailed(mediaUrl)) || (thumbUrl && FailedMediaCache.isFailed(thumbUrl)))) {
11249:                 thumbHtml = `<div class="catalog-thumb broken-media" style="background-color: #1e1e1e; display:flex; align-items:center; justify-content:center;"><span style="font-size:2em">⚠️</span></div>`;
11250:             } else if (isVid) {
11251:                 const vidUrl = f.original_url || '';
11252:                 const posterUrl = f.thumbnail_url || '';
11253:                 if (vidUrl) {
11254:                     thumbHtml = `
11255:                         <div class="catalog-thumb lazy-media-wrapper" data-src="${vidUrl}" data-type="video" style="background-color: #000;">
11256:                             <video class="lazy-load${blurClass}" preload="metadata" muted playsinline loop data-src="${vidUrl}" poster="${posterUrl}" style="width: 100%; height: 100%; object-fit: cover;"></video>
11257:                             <span class="lazy-badge" style="position:absolute; bottom:5px; right:5px; background:rgba(0,0,0,0.6); color:white; padding:2px 4px; font-size:10px; border-radius:3px;">VIDEO</span>
11258:                         </div>`;
11259:                 } else {
11260:                      thumbHtml = `<div class="catalog-thumb" style="background-color: ${bgColor}; display:flex; align-items:center; justify-content:center;"><span style="font-size:2em">⏳</span></div>`;
11261:                 }
11262:             } else {
11263:                 const imgUrl = f.thumbnail_url || f.original_url;
11264:                 if (imgUrl) {
11265:                     thumbHtml = `<div class="catalog-thumb"><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" data-src="${imgUrl}" class="lazy-load${blurClass}" style="width: 100%; height: 100%; object-fit: cover;" referrerpolicy="no-referrer"></div>`;
11266:                 } else {
11267:                     thumbHtml = `<div class="catalog-thumb" style="background-color: ${bgColor}; display:flex; align-items:center; justify-content:center;"><span style="font-size:2em">🖼️</span></div>`;
11268:                 }
11269:             }
11270:         } else {
11271:             thumbHtml = `<div class="catalog-thumb" style="background-color: ${bgColor};"><div class="catalog-ambient"><span>📝</span><small>${esc(data.content.text).substring(0, 40)}</small></div></div>`;
11272:         }
11273: 
11274:         const badges = `
11275:             ${data.is_pinned ? '<div class="cat-badge badge-pin">PIN</div>' : ''}
11276:             ${data.is_endless ? '<div class="cat-badge badge-cyclic">🔄</div>' : ''}
11277:             ${data.is_archived ? '<div class="cat-badge badge-lock">LOCK</div>' : ''}
11278:         `;
11279: 
11280:         const typeBadge = data.thread_type !== 'default' ? `<span style="color:var(--accent-primary); font-weight:bold;">[${data.thread_type.toUpperCase()}]</span> ` : '';
11281:         const title = data.thread_title || `№${threadId}`;
11282: 
11283:         const card = document.createElement('a');
11284:         card.href = `/${data.board_id}/res/${threadId}.html`;
11285:         card.className = 'catalog-item new-post-animation';
11286:         card.innerHTML = `
11287:             <div style="position:relative; width:100%; height:100%;">
11288:                 ${thumbHtml}
11289:                 ${badges}
11290:             </div>
11291:             <div class="catalog-info">
11292:                 <div class="catalog-stats-line">
11293:                     <span class="stat-replies">R: ${data.reply_count || 0}</span> <span style="opacity:0.3">|</span> 
11294:                     <span class="stat-images">I: ${files.length}</span>
11295:                 </div>
11296:                 <div class="catalog-text-content">
11297:                     <span class="catalog-subject">${typeBadge}${esc(title)}</span>
11298:                     ${esc(data.content.text)}
11299:                 </div>
11300:             </div>
11301:         `;
11302:         return card;
11303:     },
11304:      
11305: };
11306: function initTruncatePosts(el) {
11307:     const textContents = el.querySelectorAll('.post-text-content');
11308:     textContents.forEach(content => {
11309:         if (content.dataset.truncated) return; 
11310:         const MAX_HEIGHT = 400;
11311:         if (content.scrollHeight > MAX_HEIGHT) {
11312:             content.style.maxHeight = MAX_HEIGHT + 'px';
11313:             content.style.overflow = 'hidden';
11314:             content.style.position = 'relative';
11315:             content.style.maskImage = 'linear-gradient(to bottom, black 80%, transparent 100%)';
11316:             content.style.webkitMaskImage = 'linear-gradient(to bottom, black 80%, transparent 100%)';
11317:             const btn = document.createElement('div');
11318:             btn.className = 'expand-post-btn';
11319:             btn.textContent = `⬇ Читать дальше`;
11320:             btn.onclick = (e) => {
11321:                 e.stopPropagation();
11322:                 e.preventDefault();
11323:                 content.style.maxHeight = 'none';
11324:                 content.style.maskImage = 'none';
11325:                 content.style.webkitMaskImage = 'none';
11326:                 btn.remove();
11327:             };
11328:             content.parentNode.insertBefore(btn, content.nextSibling);
11329:             content.dataset.truncated = 'true';
11330:         }
11331:     });
11332: }
11333: window.initializePostFeatures = function(el) {
11334:     if (!el || el.dataset.initialized) return;
11335:     try {
11336:         if (typeof initTooltips === 'function') initTooltips(el);
11337:         if (typeof initTruncatePosts === 'function') initTruncatePosts(el);
11338:         
11339:         if (typeof AudioManager !== 'undefined') AudioManager.upgradeLegacy(el);
11340:         if (typeof window.parseTextEffects === 'function') window.parseTextEffects(el);
11341:         if (typeof processEmbeds === 'function') processEmbeds(el);
11342:         if (typeof applyAdaptiveFontSize === 'function') applyAdaptiveFontSize(el);
11343:         el.querySelectorAll('video.post-video').forEach(v => {
11344:             v.removeAttribute('onmouseover');
11345:             v.removeAttribute('onmouseout');
11346:             
11347:             v.onplay = () => {
11348:                 if (typeof AudioManager !== 'undefined') AudioManager.stopOthers(v);
11349:             };
11350:             
11351:             if (window.observeSticky) window.observeSticky(v);
11352:             if (window.videoObserver) window.videoObserver.observe(v);
11353:             
11354:             if (v.videoWidth) checkIfVideoIsNote(v);
11355:             else v.onloadedmetadata = () => checkIfVideoIsNote(v);
11356:         });
11357: 
11358:         el.querySelectorAll('img.post-image, video.post-image').forEach(img => {
11359:             const src = img.dataset.src || img.src || '';
11360:             if (typeof FailedMediaCache !== 'undefined' && FailedMediaCache.isFailed(src)) {
11361:                 const parent = img.closest('.file-thumb, .lazy-media-wrapper, .sticker-wrapper, .catalog-thumb');
11362:                 if (parent) {
11363:                     parent.classList.remove('is-loading');
11364:                     parent.classList.add('broken-media');
11365:                     parent.innerHTML = `<div class="broken-media" title="Media Unavailable" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; min-height:80px; background:#1e1e1e; color:#888; font-size:1.2em;">⚠️ Media Unavailable</div>`;
11366:                 } else {
11367:                     img.classList.add('broken-final');
11368:                     img.style.display = 'none';
11369:                 }
11370:             } else {
11371:                 img.onerror = () => handleImageError(img);
11372:             }
11373:         });
11374:         el.querySelectorAll('.file-thumb[data-type="video"], .file-thumb[data-type="gif"], .file-thumb[data-type="animation"]').forEach(wrapper => {
11375:             wrapper.style.cursor = 'pointer'; 
11376:         });
11377: 
11378:         checkPostGet(el);
11379:         generateIdenticons(el);
11380:         CrossBoardManager.resolve(el);
11381:         
11382:         if (window.UserState && window.UserState.postIds.has(el.id.replace('post-', ''))) {
11383:             el.classList.add('is-yours');
11384:         }
11385:         
11386:         if (typeof SmartLoader !== 'undefined') {
11387:             SmartLoader.scan(el);
11388:         }
11389: 
11390:     } catch (e) {
11391:         console.error("Critical: Error initializing post features:", e, el);
11392:     }
11393:     el.dataset.initialized = 'true';
11394: };
11395: window.parseTextEffects = (el) => {
11396:     let container = el.querySelector('.post-text') || el.querySelector('.post-text-content');
11397:     if (!container) return;
11398:     if (container.dataset.parsed === 'true') return;
11399:     let html = container.innerHTML;
11400:     const linkRegex = /(<a\b[^>]*>[\s\S]*?<\/a>)|(?<!["'=])(https?:\/\/[^\s<"']+)/gi;
11401:     html = html.replace(linkRegex, (match, g1, g2) => {
11402:         if (g1) return g1;
11403:         const { urlPart, suffix } = cleanUrlAndSuffix(g2);
11404:         if (!urlPart) return g2;
11405:         return `<a href="${urlPart}" target="_blank" rel="noopener" class="auto-link">${urlPart}</a>${suffix}`;
11406:     });
11407:     const simpleTags = [
11408:         { open: '\\[b\\]', close: '\\[\\/b\\]', tag: 'b' },
11409:         { open: '\\[i\\]', close: '\\[\\/i\\]', tag: 'i' },
11410:         { open: '\\[s\\]', close: '\\[\\/s\\]', tag: 's' },
11411:         { open: '\\[u\\]', close: '\\[\\/u\\]', tag: 'u' },
11412:         { open: '\\[code\\]', close: '\\[\\/code\\]', tag: 'code' },
11413:         { open: '\\[h1\\]', close: '\\[\\/h1\\]', tag: 'h3', class: 'post-heading' },
11414:         { open: '\\|\\|', close: '\\|\\|', class: 'spoiler' } 
11415:     ];
11416:     html = html.replace(/\[btn=(https?:\/\/[^\]]+)\](.*?)\[\/btn\]/gi, (match, url, text) => {
11417:         const safeUrl = url.replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
11418:         return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-small post-btn">${text}</a>`;
11419:     });
11420:     html = html.replace(/\[size=(\d+)\](.*?)\[\/size\]/gi, (match, size, content) => {
11421:         let s = parseInt(size);
11422:         if (s < 10) s = 10; if (s > 30) s = 30;
11423:         return `<span style="font-size: ${s}px;">${content}</span>`;
11424:     });
11425:     simpleTags.forEach(t => {
11426:         const regex = new RegExp(`${t.open}([\\s\\S]*?)${t.close}`, 'gi');
11427:         if (t.tag) {
11428:             html = html.replace(regex, `<${t.tag}>$1</${t.tag}>`);
11429:         } else if (t.class) {
11430:             html = html.replace(regex, `<span class="${t.class}">$1</span>`);
11431:         }
11432:     });
11433:     const effects = [
11434:         { tag: 'shake', class: 'effect-shake' },
11435:         { tag: 'rainbow', class: 'effect-rainbow' },
11436:         { tag: 'blur', class: 'effect-blur' }
11437:     ];
11438:     effects.forEach(eff => {
11439:         const regex = new RegExp(`\\[${eff.tag}\\]([\\s\\S]*?)\\[\\/${eff.tag}\\]`, 'gi');
11440:         html = html.replace(regex, `<span class="${eff.class}">$1</span>`);
11441:     });
11442:     html = html.replace(/\[glitch\]([\s\S]*?)\[\/glitch\]/gi, (match, content) => {
11443:         const clean = content.replace(/<[^>]*>/g, '');
11444:         return `<span class="effect-glitch" data-text="${clean}">${content}</span>`;
11445:     });
11446:     container.innerHTML = html;
11447:     container.dataset.parsed = 'true';
11448: };
11449: function handleImageError(img) {
11450:     if (!img) return;
11451:     img.onerror = null; // Unbind immediately to prevent synchronous 404 retry loop
11452: 
11453:     if (img.dataset.finalError) return;
11454:     img.dataset.finalError = "true";
11455: 
11456:     const parent = img.closest('.file-thumb, .lazy-media-wrapper, .sticker-wrapper, .catalog-thumb');
11457:     const currentSrc = img.src || img.dataset.src || "";
11458:     const originalUrl = parent ? (parent.href || parent.dataset.src || currentSrc) : (img.dataset.src || currentSrc);
11459: 
11460:     const renderStaticError = () => {
11461:         img.classList.add('broken-final');
11462:         if (parent) {
11463:             parent.classList.remove('is-loading');
11464:             parent.classList.add('broken-media');
11465:             parent.innerHTML = `<div class="broken-media" title="Media Unavailable" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; min-height:80px; background:#1e1e1e; color:#888; font-size:1.2em;">⚠️ Media Unavailable</div>`;
11466:         } else {
11467:             img.style.display = 'none';
11468:         }
11469:     };
11470: 
11471:     if (typeof FailedMediaCache !== 'undefined') {
11472:         if (FailedMediaCache.isFailed(originalUrl) || FailedMediaCache.isFailed(currentSrc)) {
11473:             renderStaticError();
11474:             return;
11475:         }
11476:     }
11477: 
11478:     if (!originalUrl) {
11479:         if (typeof FailedMediaCache !== 'undefined' && currentSrc) FailedMediaCache.markFailed(currentSrc);
11480:         renderStaticError();
11481:         return;
11482:     }
11483: 
11484:     let failedType = null;
11485:     if (currentSrc.includes("iili.io")) failedType = "freeimage";
11486:     else if (currentSrc.includes("ibb.co")) failedType = "imgbb";
11487:     else if (currentSrc.includes("pixhost.to")) failedType = "pixhost";
11488:     else if (currentSrc.includes("catbox.moe")) failedType = "catbox";
11489:     else if (currentSrc.includes("0x0.st")) failedType = "0x0";
11490:     else if (currentSrc.includes("telegram.org")) failedType = "telegram";
11491: 
11492:     const isLocalFile = currentSrc.includes("/files/") || originalUrl.includes("/files/") || !failedType;
11493: 
11494:     if (isLocalFile) {
11495:         if (typeof FailedMediaCache !== 'undefined') {
11496:             FailedMediaCache.markFailed(originalUrl);
11497:             FailedMediaCache.markFailed(currentSrc);
11498:         }
11499:         renderStaticError();
11500:         return;
11501:     }
11502: 
11503:     let skipped = img.dataset.skippedHosts ? img.dataset.skippedHosts.split(",") : [];
11504:     if (failedType && !skipped.includes(failedType)) {
11505:         skipped.push(failedType);
11506:     }
11507:     img.dataset.skippedHosts = skipped.join(",");
11508: 
11509:     if (skipped.length >= 6) {
11510:         if (typeof FailedMediaCache !== 'undefined') {
11511:             FailedMediaCache.markFailed(originalUrl);
11512:             FailedMediaCache.markFailed(currentSrc);
11513:         }
11514:         img.classList.add('broken-final');
11515:         img.style.display = 'none';
11516:         if (parent) {
11517:             parent.classList.remove('is-loading');
11518:             parent.classList.add('broken-media');
11519:             parent.innerHTML = `<div class="broken-media" title="Media failed"><a href="${originalUrl}" target="_blank" style="color:#fff;text-decoration:none;">📂 Скачать</a></div>`;
11520:         }
11521:         return;
11522:     }
11523: 
11524:     delete img.dataset.finalError;
11525:     try {
11526:         const loc = (typeof window !== 'undefined' && window.location) ? window.location.href : 'http://localhost';
11527:         const urlObj = new URL(originalUrl, loc);
11528:         urlObj.searchParams.set("skip", img.dataset.skippedHosts);
11529:         const newUrl = urlObj.toString();
11530: 
11531:         console.log(`[MediaRescue] Redirect failed for type: ${failedType}. Swapping to skip parameter: ${img.dataset.skippedHosts}`);
11532: 
11533:         if (img.tagName === 'VIDEO') {
11534:             img.onerror = () => handleImageError(img);
11535:             img.src = newUrl;
11536:             img.load();
11537:             return;
11538:         }
11539: 
11540:         const isVideo = (parent && (
11541:             parent.dataset.type === 'video' || 
11542:             parent.dataset.type === 'gif' || 
11543:             parent.dataset.type === 'video_note' || 
11544:             parent.dataset.type === 'animation'
11545:         ));
11546: 
11547:         if (isVideo) {
11548:             const vid = document.createElement('video');
11549:             vid.className = img.className;
11550:             vid.src = newUrl;
11551:             vid.autoplay = true;
11552:             vid.loop = true;
11553:             vid.muted = true;
11554:             vid.playsInline = true;
11555:             vid.dataset.src = originalUrl;
11556:             vid.dataset.skippedHosts = img.dataset.skippedHosts;
11557:             vid.onerror = () => handleImageError(vid);
11558:             img.replaceWith(vid);
11559:         } else {
11560:             img.onerror = () => handleImageError(img);
11561:             img.src = newUrl;
11562:         }
11563: 
11564:         if (parent) parent.classList.remove('is-loading');
11565:     } catch (e) {
11566:         if (typeof FailedMediaCache !== 'undefined') {
11567:             FailedMediaCache.markFailed(originalUrl);
11568:         }
11569:         renderStaticError();
11570:     }
11571: }
11572: function checkPostGet(el) {
11573:     const id = el.id.replace('post-', '');
11574:     const match = id.match(/(\d)\1{2,}$/);
11575:     if (match) {
11576:         const digit = match[1];
11577:         const len = match[0].length;
11578:         el.classList.add(`get-digit-${digit}`);
11579:         if (len >= 5) {
11580:             el.classList.add('get-legendary');
11581:         } else if (len === 4) {
11582:             el.classList.add('get-epic');
11583:         } else {
11584:             el.classList.add('get-rare');
11585:         }
11586:     }
11587: }
11588: function checkThreadLimit(threadContainer) {
11589:     if (!threadContainer || !threadContainer.classList.contains('thread-container')) return;
11590:     if (threadContainer.dataset.endless === 'true') return;
11591:     const statsEl = threadContainer.querySelector('.thread-stats');
11592:     if (!statsEl) return;
11593:     const text = statsEl.textContent;
11594:     const match = text.match(/(\d+)/);
11595:     if (match) {
11596:         const count = parseInt(match[1]);
11597:         const LIMIT = 600;
11598:         const oldIcon = threadContainer.querySelector('.post-header .limit-icon');
11599:         if (oldIcon) oldIcon.remove();
11600:         threadContainer.classList.remove('limit-warning', 'limit-danger', 'limit-sunk');
