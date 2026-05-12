import fortyKTags from '../../../data/datafiles-Tags/40K-Tags.json';
import aosTags from '../../../data/datafiles-Tags/AOS-Tags.json';
import { buildPatternEntries, findMatchesInText } from './ruleTagMatcher';

export { buildPatternEntries, findMatchesInText } from './ruleTagMatcher';

const _patternCache = new Map();

const LINK_CLASS =
    'rounded-sm text-primary underline decoration-primary underline-offset-2 transition-colors hover:bg-primary/10 hover:text-primary/90 hover:decoration-primary/80 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none';

export function getTagsForGame(gameKey) {
    if (gameKey === '40k' || gameKey === 'wh40k') {
        return fortyKTags;
    }

    return aosTags;
}

function rulesHref(gameKey, page) {
    const g = gameKey === '40k' || gameKey === 'wh40k' ? '40k' : 'aos';
    const params = new URLSearchParams({
        game: g,
        page: String(page),
        from: 'chat',
    });

    return `/rules?${params.toString()}`;
}

function walkAndWrap(node, patternEntries, gameKey, usedConcepts) {
    if (node.nodeType === Node.TEXT_NODE) {
        const content = node.data;

        if (!content) {
            return;
        }

        const matches = findMatchesInText(
            content,
            patternEntries,
            usedConcepts,
        );

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
                frag.appendChild(
                    document.createTextNode(content.slice(cursor, m.start)),
                );
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
    const doc = parser.parseFromString(
        `<div class="rule-tag-root">${html}</div>`,
        'text/html',
    );
    const root = doc.body.querySelector('.rule-tag-root');

    if (!root) {
        return html;
    }

    const usedConcepts = new Set();
    walkAndWrap(root, patternEntries, gameKey, usedConcepts);

    return root.innerHTML;
}
