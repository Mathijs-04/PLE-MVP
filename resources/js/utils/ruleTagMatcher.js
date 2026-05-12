const SHORT_ALIAS_MAX_LENGTH = 3;

const conceptDenyRules = {
    run: [
        {
            after: /^\s+out\s+of\b/iu,
        },
    ],
};

function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function aliasToRegex(aliasLower) {
    const words = aliasLower.split(/\s+/).filter(Boolean);

    if (words.length === 1) {
        const w = escapeRegex(words[0]);

        if (words[0].length <= SHORT_ALIAS_MAX_LENGTH) {
            return new RegExp(`\\b(${w})\\b`, 'giu');
        }

        if (words[0].length >= 5) {
            return new RegExp(`\\b(${w}(?:ing|ed|es|s)?)\\b`, 'giu');
        }

        return new RegExp(`\\b(${w}(?:s|es)?)\\b`, 'giu');
    }

    const joined = words.map((word) => escapeRegex(word)).join('\\s+');

    return new RegExp(`\\b(${joined})\\b`, 'giu');
}

function hasDeniedContext(text, match, conceptId) {
    const rules = conceptDenyRules[conceptId];

    if (!rules) {
        return false;
    }

    const before = text.slice(Math.max(0, match.index - 40), match.index);
    const after = text.slice(match.index + match[0].length, match.index + 40);

    return rules.some((rule) => {
        if (rule.before && !rule.before.test(before)) {
            return false;
        }

        if (rule.after && !rule.after.test(after)) {
            return false;
        }

        return true;
    });
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

            if (hasDeniedContext(text, m, conceptId)) {
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
