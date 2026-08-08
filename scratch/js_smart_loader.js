14340:                 const vid = document.createElement('video');
14341:                 vid.className = 'post-image lazy-load'; 
14342:                 vid.muted = true;
14343:                 vid.loop = true;
14344:                 vid.playsInline = true;
14345:                 vid.dataset.src = parent.dataset.src || parent.href;
14346:                 vid.style.objectFit = 'cover';
14347:                 vid.style.width = '100%';
14348:                 vid.style.height = '100%';
14349:                 el.replaceWith(vid);
14350:             }
14351:         });
14352:         if (!this.observer) { this.init(); return; }
14353:         scope.querySelectorAll('img.lazy-load, video.lazy-load').forEach(img => {
14354:             const src = img.dataset.src || img.src || '';
14355:             if (typeof FailedMediaCache !== 'undefined' && FailedMediaCache.isFailed(src)) {
14356:                 img.classList.add('broken-final');
14357:                 const parent = img.closest('.file-thumb, .lazy-media-wrapper, .sticker-wrapper, .catalog-thumb');
14358:                 if (parent) {
14359:                     parent.classList.remove('is-loading');
14360:                     parent.classList.add('broken-media');
14361:                     parent.innerHTML = `<div class="broken-media" title="Media Unavailable" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; min-height:80px; background:#1e1e1e; color:#888; font-size:1.2em;">⚠️ Media Unavailable</div>`;
14362:                 }
14363:                 return;
14364:             }
14365:             if (img.dataset.observed) return;
14366:             img.dataset.observed = "true";
14367:             this.observer.observe(img);
14368:         });
14369:     },
14370:     enqueue(img) {
14371:         if (!img) return;
14372:         const targetSrc = img.dataset.src || img.src;
14373:         if (typeof FailedMediaCache !== 'undefined' && FailedMediaCache.isFailed(targetSrc)) {
14374:             img.classList.add('broken-final');
14375:             const parent = img.closest('.file-thumb, .lazy-media-wrapper');
14376:             if (parent) {
14377:                 parent.classList.remove('is-loading');
14378:                 parent.classList.add('broken-media');
14379:                 parent.innerHTML = `<div class="broken-media" title="Media Unavailable" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; min-height:80px; background:#1e1e1e; color:#888; font-size:1.2em;">⚠️ Media Unavailable</div>`;
14380:             }
14381:             return;
14382:         }
14383:         if (this.queue.includes(img)) return;
14384:         img.dataset.queued = "true";
14385:         this.queue.unshift(img);
14386:         this.process();
14387:     },
14388:     process() {
14389:         if (this.activeCount >= this.maxConcurrent || this.queue.length === 0) return;
14390:         const img = this.queue.shift();
14391:         if (!img.isConnected) {
14392:             this.process();
14393:             return;
14394:         }
14395:         let targetSrc = img.dataset.src;
14396:         const parent = img.closest('.file-thumb, .lazy-media-wrapper');
14397:         if (!targetSrc || targetSrc.includes('undefined') || targetSrc.includes('null') || (typeof FailedMediaCache !== 'undefined' && FailedMediaCache.isFailed(targetSrc))) {
14398:             if (targetSrc && typeof FailedMediaCache !== 'undefined' && FailedMediaCache.isFailed(targetSrc)) {
14399:                 img.classList.add('broken-final');
14400:                 if (parent) {
14401:                     parent.classList.remove('is-loading');
14402:                     parent.classList.add('broken-media');
14403:                     parent.innerHTML = `<div class="broken-media" title="Media Unavailable" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; min-height:80px; background:#1e1e1e; color:#888; font-size:1.2em;">⚠️ Media Unavailable</div>`;
14404:                 }
14405:             }
14406:             this.activeCount--;
14407:             if (parent) parent.classList.remove('is-loading');
14408:             this.process();
14409:             return;
14410:         }
14411:         this.activeCount++;
14412:         if (parent) parent.classList.add('is-loading');
14413:         let targetSrcOriginal = img.dataset.src;
14414: 
14415:         if (img.tagName !== 'VIDEO') {
14416:             const onLoad = () => this.onLoadFinished(img, parent, true);
14417:             const onError = () => this.onLoadFinished(img, parent, false);
14418:             img.onload = onLoad;
14419:             img.onerror = onError;
14420:             img.src = targetSrc;
14421:         } else {
14422:             img.onloadeddata = () => {
14423:                 img.classList.add('loaded');
14424:                 if (parent) parent.classList.remove('is-loading');
14425:             };
14426:             img.onerror = () => {
14427:                  if (parent) {
14428:                     parent.classList.remove('is-loading');
14429:                     parent.classList.add('broken-media');
14430:                     parent.innerHTML = '<div style="font-size:2em; color:#555;">⚠️</div>';
14431:                 }
14432:             };
14433:             
14434:             img.src = targetSrc;
14435:             img.load();
14436:             this.activeCount--;
14437:             this.process();
14438:         }
14439:     },
14440:     onLoadFinished(img, parent, success) {
14441:         this.activeCount--;
14442:         if (this.observer) this.observer.unobserve(img);
14443:         
14444:         if (success) {
14445:             img.dataset.loaded = "true";
14446:             img.classList.add('loaded');
14447:             
14448:             const thumb = img.closest('.file-thumb, .lazy-media-wrapper');
14449:             if (thumb) {
14450:                 thumb.classList.remove('is-loading');
14451:                 thumb.classList.add('loaded');
14452:                 
14453:                 const canvas = thumb.querySelector('canvas');
14454:                 if (canvas) {
14455:                     canvas.remove();
14456:                 }
14457:             }
14458:         } else {
14459:             const rect = img.getBoundingClientRect();
14460:             const isVisible = (rect.top < window.innerHeight + 1500 && rect.bottom > -1500);
14461: 
14462:             if (!isVisible) {
14463:                 delete img.dataset.queued;
14464:                 if (parent) parent.classList.remove('is-loading');
14465:                 delete img.dataset.observed; 
14466:                 if (this.observer) this.observer.observe(img);
14467:                 img.dataset.observed = "true";
14468:                 
14469:                 this.process();
14470:                 return;
14471:             }
14472: 
14473:             if (img.classList.contains('post-sticker') && !img.dataset.triedVideo) {
14474:                 img.dataset.triedVideo = "true";
14475:                 const vid = document.createElement('video');
14476:                 vid.className = img.className; 
14477:                 vid.classList.add('loaded'); 
14478:                 vid.src = img.dataset.src || img.src;
14479:                 vid.autoplay = true;
14480:                 vid.loop = true;
14481:                 vid.muted = true;
14482:                 vid.playsInline = true;
14483:                 vid.setAttribute('webkit-playsinline', 'true');
14484:                 vid.style.display = 'block';
14485:                 vid.style.maxWidth = '100%';
14486:                 vid.style.maxHeight = '150px';
14487:                 vid.onerror = () => {
14488:                     const errDiv = document.createElement('div');
14489:                     errDiv.className = 'broken-media';
14490:                     errDiv.innerHTML = '<div class="broken-media" title="Media Unavailable" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; min-height:80px; background:#1e1e1e; color:#888; font-size:1.2em;">⚠️ Media Unavailable</div>';
14491:                     vid.replaceWith(errDiv);
14492:                 };
14493:                 img.replaceWith(vid);
14494:                 if (parent) parent.classList.remove('is-loading');
14495:                 this.process(); 
14496:                 return;
14497:             } else {
14498:                 const baseUrl = img.dataset.src || img.src;
14499:                 if (baseUrl && typeof FailedMediaCache !== 'undefined') {
14500:                     FailedMediaCache.markFailed(baseUrl);
14501:                 }
14502:                 img.classList.add('broken-final');
14503:                 if (typeof handleImageError === 'function') {
14504:                     handleImageError(img);
14505:                 } else if (parent) {
14506:                     parent.classList.remove('is-loading');
14507:                     parent.classList.add('broken-media');
14508:                     parent.innerHTML = `<div class="broken-media" title="Media Unavailable" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; min-height:80px; background:#1e1e1e; color:#888; font-size:1.2em;">⚠️ Media Unavailable</div>`;
14509:                 }
14510:             }
14511:         }
14512:         this.process();
14513:     }
14514: };
14515: document.addEventListener('DOMContentLoaded', () => SmartLoader.init(document));
14516: const _oldInitPost = window.initializePostFeatures;
14517: window.initializePostFeatures = function(el) {
14518:     if (typeof _oldInitPost === 'function') _oldInitPost(el); 
14519:     if (typeof SmartLoader !== 'undefined') {
14520:         SmartLoader.scan(el);
14521:     }
14522: };
14523: document.addEventListener('click', async (e) => {
14524:     const btn = e.target.closest('.action-copy-link');
14525:     if (!btn) return;
14526:     if (navigator.share) {
14527:         e.preventDefault();
14528:         const postNum = btn.dataset.postNum;
14529:         const boardId = btn.dataset.boardId || document.querySelector('input[name="board_id"]')?.value;
14530:         const threadId = btn.dataset.threadId;
14531:         const url = `${window.location.origin}/${boardId}/res/${threadId}.html#post-${postNum}`;
14532:         try {
14533:             await navigator.share({
14534:                 title: `ТГАЧ /${boardId}/ #${postNum}`,
14535:                 text: `Чекни этот пост:`,
14536:                 url: url
14537:             });
14538:         } catch (err) {
14539:         }
14540:     }
14541: });
14542: document.addEventListener('mousedown', createRipple);
14543: function createRipple(e) {
14544:     const target = e.target.closest('.btn, .header-btn, .board-card, .board-nav a, .dock-btn, .dock-tool-btn');
14545:     if (!target) return;
14546:     
14547:     const circle = document.createElement('span');
14548:     const diameter = Math.max(target.clientWidth, target.clientHeight);
14549:     const radius = diameter / 2;
14550:     const rect = target.getBoundingClientRect();
