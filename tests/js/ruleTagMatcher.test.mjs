import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
    buildPatternEntries,
    findMatchesInText,
} from '../../resources/js/utils/ruleTagMatcher.js';

const tags = {
    run: {
        page: 14,
        aliases: ['run'],
    },
    pile_in_move: {
        page: 16,
        aliases: ['pile in', 'pile-in'],
    },
    in_combat: {
        page: 10,
        aliases: ['in combat'],
    },
    combat_range: {
        page: 10,
        aliases: ['combat range'],
    },
};

function matchesFor(text) {
    const entries = buildPatternEntries(tags);

    return findMatchesInText(text, entries, new Set()).map((match) => ({
        text: text.slice(match.start, match.end),
        page: match.page,
        conceptId: match.conceptId,
    }));
}

describe('rule tag matcher', () => {
    it('does not link ordinary prose forms of run', () => {
        const matches = matchesFor(
            'If one player runs out of eligible units, the other player keeps picking eligible units until none remain.',
        );

        assert.deepEqual(matches, []);
    });

    it('links run in a rule context', () => {
        const matches = matchesFor('A unit can use Run in your movement phase.');

        assert.deepEqual(matches, [
            {
                text: 'Run',
                page: 14,
                conceptId: 'run',
            },
        ]);
    });

    it('links precise multi-word and hyphenated contexts', () => {
        const matches = matchesFor(
            'A unit can make a pile-in move while it is in combat.',
        );

        assert.deepEqual(matches, [
            {
                text: 'pile-in',
                page: 16,
                conceptId: 'pile_in_move',
            },
            {
                text: 'in combat',
                page: 10,
                conceptId: 'in_combat',
            },
        ]);
    });

    it('keeps distinct concepts and links each concept once', () => {
        const matches = matchesFor(
            'Combat range matters in combat, but combat range is only linked once.',
        );

        assert.deepEqual(matches, [
            {
                text: 'Combat range',
                page: 10,
                conceptId: 'combat_range',
            },
            {
                text: 'in combat',
                page: 10,
                conceptId: 'in_combat',
            },
        ]);
    });
});
