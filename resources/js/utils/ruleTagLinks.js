import fortyKTags from '../../../data/datafiles-Tags/40K-Tags.json';
import aosTags from '../../../data/datafiles-Tags/AOS-Tags.json';
import { rules } from '@/routes';

const _patternCache = new Map();

const LINK_CLASS =
    'underline decoration-primary underline-offset-2 text-primary hover:text-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm';

export function getTagsForGame(gameKey) {
    if (gameKey === '40k' || gameKey === 'wh40k') {
        return fortyKTags;
    }

    return aosTags;
}

function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function aliasToRegex(aliasLower) {
    const words = aliasLower.split(/\s+/).filter(Boolean);

    if (words.length === 1) {
        const w = escapeRegex(words[0]);

        if (words[0].length >= 5) {
            return new RegExp(`\\b(${w}(?:ing|ed|es|s)?)\\b`, 'giu');
        }

        return new RegExp(`\\b(${w}(?:s|es)?)\\b`, 'giu');
    }

    const joined = words.map((word) => escapeRegex(word)).join('\\s+');

    return new RegExp(`\\b(${joined})\\b`, 'giu');
}

export function buildPatternEntries(tagsJson) {
    const seen = new Set();
    const entries = [];

    for (const [key, def] of Object.entries(tagsJson)) {
        const page = def.page;
        const list = [...(def.aliases || [])];
        const keyPhrase = key.replace(/_/g, ' ');
        list.push(keyPhrase);

        for (const alias of list) {
            const trimmed = alias.trim();

            if (!trimmed) {
                continue;
            }

            const dedupeKey = `${trimmed.toLowerCase()}|${page}`;

            if (seen.has(dedupeKey)) {
                continue;
            }

            seen.add(dedupeKey);
            const re = aliasToRegex(trimmed.toLowerCase());
            entries.push({ re, page, sortLen: trimmed.length, conceptId: key });
        }
    }

    entries.sort((a, b) => b.sortLen - a.sortLen);

    return entries;
}

export function findMatchesInText(text, patternEntries, usedConcepts) {
    const raw = [];

    for (const { re, page, conceptId } of patternEntries) {
        const r = new RegExp(re.source, re.flags);
        let m;

        while ((m = r.exec(text)) !== null) {
            if (m[0].length === 0) {
                if (r.lastIndex === m.index) {
                    r.lastIndex += 1;
                }

                continue;
            }

            raw.push({
                start: m.index,
                end: m.index + m[0].length,
                page,
                conceptId,
            });
        }
    }

    raw.sort((a, b) => {
        if (a.start !== b.start) {
            return a.start - b.start;
        }

        return b.end - b.start - (a.end - a.start);
    });

    const selected = [];
    let lastEnd = -1;

    for (const m of raw) {
        if (m.start >= lastEnd && !usedConcepts.has(m.conceptId)) {
            selected.push(m);
            lastEnd = m.end;
            usedConcepts.add(m.conceptId);
        }
    }

    return selected;
}

function rulesHref(gameKey, page) {
    const g = gameKey === '40k' || gameKey === 'wh40k' ? '40k' : 'aos';

    return rules.url({
        query: {
            game: g,
            page,
        },
    });
}

function walkAndWrap(node, patternEntries, gameKey, usedConcepts) {
    if (node.nodeType === Node.TEXT_NODE) {
        const content = node.data;

        if (!content) {
            return;
        }

        const matches = findMatchesInText(content, patternEntries, usedConcepts);

        if (matches.length === 0) {
            return;
        }

        const parent = node.parentNode;

        if (!parent) {
            return;
        }

        const frag = document.createDocumentFragment();
        let cursor = 0;

        for (const m of matches) {
            if (m.start > cursor) {
                frag.appendChild(document.createTextNode(content.slice(cursor, m.start)));
            }

            const a = document.createElement('a');
            a.href = rulesHref(gameKey, m.page);
            a.className = LINK_CLASS;
            a.textContent = content.slice(m.start, m.end);
            frag.appendChild(a);
            cursor = m.end;
        }

        if (cursor < content.length) {
            frag.appendChild(document.createTextNode(content.slice(cursor)));
        }

        parent.replaceChild(frag, node);

        return;
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
        return;
    }

    const tag = node.nodeName;

    if (tag === 'PRE' || tag === 'CODE' || tag === 'A') {
        return;
    }

    const children = [...node.childNodes];

    for (const child of children) {
        walkAndWrap(child, patternEntries, gameKey, usedConcepts);
    }
}

export function wrapRuleTagLinks(html, gameKey, tagsJson) {
    if (import.meta.env.SSR || typeof window === 'undefined' || !html) {
        return html;
    }

    const cacheKey = gameKey === '40k' || gameKey === 'wh40k' ? '40k' : 'aos';

    if (!_patternCache.has(cacheKey)) {
        _patternCache.set(cacheKey, buildPatternEntries(tagsJson));
    }

    const patternEntries = _patternCache.get(cacheKey);

    if (patternEntries.length === 0) {
        return html;
    }

    const parser = new DOMParser();
    const doc = parser.parseFromString(`<div class="rule-tag-root">${html}</div>`, 'text/html');
    const root = doc.body.querySelector('.rule-tag-root');

    if (!root) {
        return html;
    }

    const usedConcepts = new Set();
    walkAndWrap(root, patternEntries, gameKey, usedConcepts);

    return root.innerHTML;
}
