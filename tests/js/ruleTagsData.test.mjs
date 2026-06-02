import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { describe, it } from 'node:test';

async function readJson(path) {
    return JSON.parse(await readFile(new URL(path, import.meta.url), 'utf8'));
}

function assertTagData(tags, maxPage) {
    assert.ok(Object.keys(tags).length > 0);

    for (const [conceptId, definition] of Object.entries(tags)) {
        assert.match(conceptId, /^[a-z0-9_]+$/);
        assert.equal(Number.isInteger(definition.page), true);
        assert.equal(definition.page >= 1, true);
        assert.equal(definition.page <= maxPage, true);
        assert.equal(Array.isArray(definition.aliases), true);
        assert.equal(definition.aliases.length > 0, true);

        for (const alias of definition.aliases) {
            assert.equal(typeof alias, 'string');
            assert.notEqual(alias.trim(), '');
        }
    }
}

describe('rule tag data', () => {
    it('keeps 40K tags valid for the 11th edition PDF', async () => {
        const tags = await readJson('../../data/datafiles-Tags/40K-Tags.json');

        assertTagData(tags, 88);
    });

    it('keeps AoS tags valid for the served PDF', async () => {
        const tags = await readJson('../../data/datafiles-Tags/AOS-Tags.json');

        assertTagData(tags, 100);
    });
});
