"""
Agent-OS Page Analyzer
Extracts structured information from web pages for AI agents.
Summarizes content, finds key data, extracts tables, forms, and metadata.
"""
import logging
import re
from typing import Dict, Any

logger = logging.getLogger("agent-os.page_analyzer")


class PageAnalyzer:
    """
    Analyze web pages and extract structured information.
    No external AI API needed — pure DOM analysis + heuristics.
    """

    def __init__(self, browser):
        self.browser = browser

    async def summarize(self, page_id: str = "main") -> Dict[str, Any]:
        """
        Generate a structured summary of the current page.
        Returns key info: title, headings, main content, links, forms, metadata.
        """
        page = self.browser._pages.get(page_id, self.browser.page)

        analysis = await page.evaluate("""() => {
            const result = {};

            // 1. Basic metadata
            result.title = document.title;
            result.url = window.location.href;
            result.domain = window.location.hostname;

            // Meta tags
            result.meta = {};
            document.querySelectorAll('meta').forEach(m => {
                const name = m.getAttribute('name') || m.getAttribute('property') || m.getAttribute('http-equiv');
                const content = m.getAttribute('content');
                if (name && content) result.meta[name] = content;
            });

            // 2. Headings hierarchy
            result.headings = [];
            document.querySelectorAll('h1, h2, h3').forEach(h => {
                const text = h.textContent.trim();
                if (text && text.length < 200) {
                    result.headings.push({level: parseInt(h.tagName[1]), text: text});
                }
            });

            // 3. Main content extraction
            const mainSelectors = ['main', 'article', '[role="main"]', '.content', '.post', '.article', '#content', '#main'];
            let mainEl = null;
            for (const sel of mainSelectors) {
                mainEl = document.querySelector(sel);
                if (mainEl) break;
            }

            if (!mainEl) mainEl = document.body;

            // Get paragraphs from main content
            result.paragraphs = [];
            (mainEl || document.body).querySelectorAll('p').forEach(p => {
                const text = p.textContent.trim();
                if (text.length > 30 && text.length < 2000) {
                    result.paragraphs.push(text);
                }
            });

            // 4. Extract key text (first N meaningful paragraphs)
            result.main_text = result.paragraphs.slice(0, 10).join('\\n\\n');

            // Word count
            const allText = result.main_text || '';
            result.word_count = allText.split(/\\s+/).filter(w => w.length > 0).length;

            // 5. Navigation elements
            result.nav_links = [];
            document.querySelectorAll('nav a, [role="navigation"] a, header a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (text && href && text.length < 100) {
                    result.nav_links.push({text, href});
                }
            });

            // 6. All links categorized
            const links = {external: [], internal: [], anchors: [], javascript: []};
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href;
                const text = (a.textContent || a.title || '').trim().substring(0, 100);
                if (href.startsWith('javascript:')) {
                    links.javascript.push({text, href});
                } else if (href.startsWith('#')) {
                    links.anchors.push({text, href});
                } else if (href.includes(window.location.hostname)) {
                    links.internal.push({text, href});
                } else if (href.startsWith('http')) {
                    links.external.push({text, href});
                }
            });
            result.links = {
                internal_count: links.internal.length,
                external_count: links.external.length,
                anchor_count: links.anchors.length,
                top_internal: links.internal.slice(0, 10),
                top_external: links.external.slice(0, 10),
            };

            // 7. Forms
            result.forms = [];
            document.querySelectorAll('form').forEach(form => {
                const fields = [];
                form.querySelectorAll('input, textarea, select').forEach(inp => {
                    fields.push({
                        tag: inp.tagName.toLowerCase(),
                        type: inp.type || 'text',
                        name: inp.name || '',
                        id: inp.id || '',
                        placeholder: inp.placeholder || '',
                        required: inp.required,
                        label: '',
                    });
                });

                // Find labels
                form.querySelectorAll('label').forEach(label => {
                    const forId = label.htmlFor;
                    if (forId) {
                        const field = fields.find(f => f.id === forId);
                        if (field) field.label = label.textContent.trim();
                    }
                });

                result.forms.push({
                    action: form.action || window.location.href,
                    method: form.method || 'GET',
                    fields: fields,
                    submit_buttons: Array.from(form.querySelectorAll('button[type="submit"], input[type="submit"]'))
                        .map(b => b.textContent || b.value || 'Submit'),
                });
            });

            // 8. Images
            result.images = [];
            document.querySelectorAll('img').forEach(img => {
                if (img.src && img.naturalWidth > 50) {
                    result.images.push({
                        src: img.src,
                        alt: img.alt || '',
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                    });
                }
            });

            // 9. Tables
            result.tables = [];
            document.querySelectorAll('table').forEach(table => {
                const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                const rows = [];
                table.querySelectorAll('tr').forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim().substring(0, 200));
                    if (cells.length > 0) rows.push(cells);
                });
                if (headers.length > 0 || rows.length > 0) {
                    result.tables.push({headers, row_count: rows.length, sample_rows: rows.slice(0, 5)});
                }
            });

            // 10. Open Graph / Social metadata
            result.social = {};
            document.querySelectorAll('meta[property^="og:"], meta[property^="twitter:"]').forEach(m => {
                result.social[m.getAttribute('property')] = m.getAttribute('content');
            });

            // 11. Page load performance
            if (window.performance && window.performance.timing) {
                const t = window.performance.timing;
                result.performance = {
                    load_time_ms: t.loadEventEnd - t.navigationStart,
                    dom_ready_ms: t.domContentLoadedEventEnd - t.navigationStart,
                    first_byte_ms: t.responseStart - t.navigationStart,
                };
            }

            // 12. Technology detection (basic)
            result.technologies = [];
            const checks = {
                'jQuery': () => !!window.jQuery,
                'React': () => !!document.querySelector('[data-reactroot]') || !!window.__REACT_DEVTOOLS_GLOBAL_HOOK__,
                'Vue': () => !!window.__VUE__,
                'Angular': () => !!document.querySelector('[ng-version]') || !!window.ng,
                'Next.js': () => !!document.querySelector('#__next'),
                'Gatsby': () => !!document.querySelector('#___gatsby'),
                'Bootstrap': () => !!document.querySelector('.container') && !!document.querySelector('.row'),
                'Tailwind': () => !!document.querySelector('[class*="tw-"]') || document.querySelector('link[href*="tailwind"]'),
                'WordPress': () => !!document.querySelector('meta[name="generator"][content*="WordPress"]'),
                'Google Analytics': () => !!window.ga || !!window.gtag || !!document.querySelector('script[src*="google-analytics"]'),
                'Google Tag Manager': () => !!window.dataLayer,
                'Cloudflare': () => document.querySelector('meta[name="cf-2fa-verify"]') !== null,
            };
            for (const [name, check] of Object.entries(checks)) {
                try { if (check()) result.technologies.push(name); } catch(e) {}
            }

            return result;
        }""")

        # Add readability metrics
        text = analysis.get("main_text", "")
        analysis["readability"] = self._analyze_readability(text)

        return {"status": "success", "analysis": analysis}

    async def extract_tables(self, page_id: str = "main") -> Dict[str, Any]:
        """Extract all tables from the page as structured data."""
        page = self.browser._pages.get(page_id, self.browser.page)

        tables = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('table').forEach((table, idx) => {
                const headers = Array.from(table.querySelectorAll('thead th, tr:first-child th'))
                    .map(th => th.textContent.trim());

                const rows = [];
                const bodyRows = table.querySelectorAll('tbody tr, tr:not(:first-child)');
                bodyRows.forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim());
                    if (cells.length > 0) rows.push(cells);
                });

                if (rows.length > 0) {
                    results.push({
                        index: idx,
                        headers: headers,
                        rows: rows,
                        row_count: rows.length,
                        col_count: headers.length || (rows[0] ? rows[0].length : 0),
                    });
                }
            });
            return results;
        }""")

        return {"status": "success", "tables": tables, "count": len(tables)}

    async def extract_structured_data(self, page_id: str = "main") -> Dict[str, Any]:
        """Extract JSON-LD, Microdata, and RDFa structured data."""
        page = self.browser._pages.get(page_id, self.browser.page)

        data = await page.evaluate("""() => {
            const result = {json_ld: [], microdata: [], rdfa: []};

            // JSON-LD
            document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
                try {
                    result.json_ld.push(JSON.parse(script.textContent));
                } catch(e) {}
            });

            // Microdata (itemscope/itemtype)
            document.querySelectorAll('[itemscope]').forEach(el => {
                const item = {
                    type: el.getAttribute('itemtype') || '',
                    properties: {}
                };
                el.querySelectorAll('[itemprop]').forEach(prop => {
                    const name = prop.getAttribute('itemprop');
                    const value = prop.getAttribute('content') || prop.getAttribute('href') || prop.textContent.trim();
                    if (name) item.properties[name] = value.substring(0, 500);
                });
                if (Object.keys(item.properties).length > 0) {
                    result.microdata.push(item);
                }
            });

            return result;
        }""")

        return {"status": "success", "structured_data": data}

    async def find_emails(self, page_id: str = "main") -> Dict[str, Any]:
        """Find all email addresses on the page."""
        page = self.browser._pages.get(page_id, self.browser.page)

        emails = await page.evaluate("""() => {
            const text = document.body.innerText;
            const html = document.body.innerHTML;
            const combined = text + ' ' + html;
            const regex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
            const matches = combined.match(regex) || [];
            return [...new Set(matches)];
        }""")

        return {"status": "success", "emails": emails, "count": len(emails)}

    async def find_phone_numbers(self, page_id: str = "main") -> Dict[str, Any]:
        """Find phone numbers on the page."""
        page = self.browser._pages.get(page_id, self.browser.page)

        phones = await page.evaluate("""() => {
            const text = document.body.innerText;
            // Remove IP addresses before matching phone numbers
            const cleanedText = text.replace(/\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b/g, ' ');
            const patterns = [
                /\\+?\\d{1,3}[-.\\s]?\\(?\\d{1,4}\\)?[-.\\s]?\\d{1,4}[-.\\s]?\\d{1,9}/g,
                /\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}/g,
                /\\d{3}[-.\\s]\\d{3}[-.\\s]\\d{4}/g,
            ];
            const all = [];
            patterns.forEach(p => {
                const m = cleanedText.match(p) || [];
                all.push(...m);
            });
            return [...new Set(all)].filter(n => n.replace(/\\D/g, '').length >= 7);
        }""")

        return {"status": "success", "phones": phones, "count": len(phones)}

    async def accessibility_check(self, page_id: str = "main") -> Dict[str, Any]:
        """Basic accessibility audit of the page."""
        page = self.browser._pages.get(page_id, self.browser.page)

        audit = await page.evaluate("""() => {
            const issues = [];

            // Images without alt text
            document.querySelectorAll('img:not([alt])').forEach(img => {
                issues.push({type: 'missing_alt', severity: 'high', element: 'img', src: img.src.substring(0, 100)});
            });

            // Empty alt text on informative images
            document.querySelectorAll('img[alt=""]').forEach(img => {
                if (img.width > 100 || img.height > 100) {
                    issues.push({type: 'empty_alt', severity: 'medium', element: 'img', src: img.src.substring(0, 100)});
                }
            });

            // Form inputs without labels
            document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"])').forEach(inp => {
                const hasLabel = inp.id && document.querySelector(`label[for="${inp.id}"]`);
                const hasAriaLabel = inp.getAttribute('aria-label');
                const hasAriaLabelledBy = inp.getAttribute('aria-labelledby');
                if (!hasLabel && !hasAriaLabel && !hasAriaLabelledBy) {
                    issues.push({type: 'missing_label', severity: 'high', element: 'input', name: inp.name || inp.id});
                }
            });

            // Missing lang attribute
            if (!document.documentElement.lang) {
                issues.push({type: 'missing_lang', severity: 'medium', element: 'html'});
            }

            // Empty links
            document.querySelectorAll('a').forEach(a => {
                const text = (a.textContent || '').trim();
                const ariaLabel = a.getAttribute('aria-label');
                const title = a.getAttribute('title');
                const img = a.querySelector('img[alt]');
                if (!text && !ariaLabel && !title && !img) {
                    issues.push({type: 'empty_link', severity: 'medium', element: 'a', href: a.href.substring(0, 100)});
                }
            });

            // Low contrast (basic check)
            // Skipped — needs computed styles for every element

            // Heading hierarchy
            let prevLevel = 0;
            document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
                const level = parseInt(h.tagName[1]);
                if (level > prevLevel + 1 && prevLevel > 0) {
                    issues.push({type: 'heading_skip', severity: 'low', element: h.tagName, text: h.textContent.trim().substring(0, 50)});
                }
                prevLevel = level;
            });

            // No h1
            if (!document.querySelector('h1')) {
                issues.push({type: 'missing_h1', severity: 'medium', element: 'page'});
            }

            return {
                total_issues: issues.length,
                by_severity: {
                    high: issues.filter(i => i.severity === 'high').length,
                    medium: issues.filter(i => i.severity === 'medium').length,
                    low: issues.filter(i => i.severity === 'low').length,
                },
                issues: issues.slice(0, 50),
            };
        }""")

        return {"status": "success", "audit": audit}

    async def seo_audit(self, page_id: str = "main") -> Dict[str, Any]:
        """Basic SEO audit of the page."""
        page = self.browser._pages.get(page_id, self.browser.page)

        audit = await page.evaluate("""() => {
            const result = {score: 100, issues: [], passed: []};

            // Title
            const title = document.title;
            if (!title) {
                result.issues.push({type: 'missing_title', severity: 'critical', message: 'Page has no <title>'});
                result.score -= 20;
            } else if (title.length < 30 || title.length > 60) {
                result.issues.push({type: 'title_length', severity: 'medium', message: `Title is ${title.length} chars (ideal: 30-60)`});
                result.score -= 5;
            } else {
                result.passed.push('Title tag present and good length');
            }

            // Meta description
            const metaDesc = document.querySelector('meta[name="description"]');
            if (!metaDesc) {
                result.issues.push({type: 'missing_meta_desc', severity: 'high', message: 'No meta description'});
                result.score -= 15;
            } else if (metaDesc.content.length < 120 || metaDesc.content.length > 160) {
                result.issues.push({type: 'meta_desc_length', severity: 'low', message: `Meta description is ${metaDesc.content.length} chars (ideal: 120-160)`});
                result.score -= 3;
            } else {
                result.passed.push('Meta description present and good length');
            }

            // H1
            const h1s = document.querySelectorAll('h1');
            if (h1s.length === 0) {
                result.issues.push({type: 'missing_h1', severity: 'high', message: 'No H1 tag found'});
                result.score -= 10;
            } else if (h1s.length > 1) {
                result.issues.push({type: 'multiple_h1', severity: 'medium', message: `${h1s.length} H1 tags found (should be 1)`});
                result.score -= 5;
            } else {
                result.passed.push('Single H1 tag present');
            }

            // Images without alt
            const imgsNoAlt = document.querySelectorAll('img:not([alt])').length;
            if (imgsNoAlt > 0) {
                result.issues.push({type: 'images_no_alt', severity: 'medium', message: `${imgsNoAlt} images without alt text`});
                result.score -= Math.min(10, imgsNoAlt * 2);
            } else {
                result.passed.push('All images have alt text');
            }

            // Canonical URL
            const canonical = document.querySelector('link[rel="canonical"]');
            if (!canonical) {
                result.issues.push({type: 'missing_canonical', severity: 'medium', message: 'No canonical URL set'});
                result.score -= 5;
            } else {
                result.passed.push('Canonical URL set');
            }

            // Open Graph
            const ogTitle = document.querySelector('meta[property="og:title"]');
            if (!ogTitle) {
                result.issues.push({type: 'missing_og', severity: 'low', message: 'No Open Graph tags'});
                result.score -= 3;
            } else {
                result.passed.push('Open Graph tags present');
            }

            // Viewport
            const viewport = document.querySelector('meta[name="viewport"]');
            if (!viewport) {
                result.issues.push({type: 'missing_viewport', severity: 'high', message: 'No viewport meta tag (mobile unfriendly)'});
                result.score -= 10;
            } else {
                result.passed.push('Viewport meta tag present');
            }

            // Schema.org structured data
            const jsonLd = document.querySelectorAll('script[type="application/ld+json"]');
            if (jsonLd.length === 0) {
                result.issues.push({type: 'no_structured_data', severity: 'low', message: 'No JSON-LD structured data'});
                result.score -= 3;
            } else {
                result.passed.push(`${jsonLd.length} JSON-LD block(s) found`);
            }

            result.score = Math.max(0, result.score);
            return result;
        }""")

        return {"status": "success", "seo": audit}

    def _analyze_readability(self, text: str) -> Dict[str, Any]:
        """Analyze text readability."""
        if not text:
            return {"score": 0, "level": "unknown"}

        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        words = text.split()

        if not sentences or not words:
            return {"score": 0, "level": "unknown"}

        avg_sentence_len = len(words) / len(sentences)

        # Simple syllable count heuristic
        def count_syllables(word):
            word = word.lower()
            count = len(re.findall(r'[aeiouy]+', word))
            return max(1, count)

        total_syllables = sum(count_syllables(w) for w in words)
        avg_syllables = total_syllables / len(words)

        # Flesch Reading Ease approximation
        score = 206.835 - (1.015 * avg_sentence_len) - (84.6 * avg_syllables)
        score = max(0, min(100, score))

        if score >= 80:
            level = "easy"
        elif score >= 60:
            level = "standard"
        elif score >= 40:
            level = "moderate"
        elif score >= 20:
            level = "difficult"
        else:
            level = "very_difficult"

        return {
            "score": round(score, 1),
            "level": level,
            "word_count": len(words),
            "sentence_count": len(sentences),
            "avg_sentence_length": round(avg_sentence_len, 1),
            "avg_syllables_per_word": round(avg_syllables, 1),
        }
