<script setup lang="js">
import { computed, ref } from 'vue';
import { Head } from '@inertiajs/vue3';
import AppLayout from '@/layouts/AppLayout.vue';
import { dashboard } from '@/routes';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const breadcrumbs = [
    {
        title: 'Dashboard',
        href: dashboard(),
    },
];

const question = ref('');
const game = ref('aos');
const loading = ref(false);
const error = ref('');
const answer = ref('');

const escapeHtml = (value) => {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
};

const renderMarkdown = (markdown) => {
    const input = String(markdown ?? '');
    const escaped = escapeHtml(input);

    const codeBlocks = [];
    const tokenized = escaped.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const i = codeBlocks.length;
        const language = lang ? ` language-${String(lang)}` : '';
        codeBlocks.push(
            `<pre class="my-3 overflow-x-auto rounded-lg bg-sidebar/10 p-3 ring-1 ring-sidebar-border/70"><code class="${language} whitespace-pre">${code}</code></pre>`,
        );
        return `@@CODEBLOCK_${i}@@`;
    });

    const renderInline = (value) => {
        let html = value;

        html = html.replace(/`([^`]+)`/g, '<code class="rounded bg-sidebar/10 px-1 py-0.5 ring-1 ring-sidebar-border/70">$1</code>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>');
        html = html.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, '$1<em class="italic">$2</em>');

        return html;
    };

    const lines = tokenized.split('\n');
    const parts = [];
    let i = 0;

    const flushParagraph = (paragraphLines) => {
        const text = paragraphLines.join('\n').trimEnd();
        if (!text) return;
        parts.push(
            `<p class="my-2 whitespace-pre-wrap leading-relaxed">${renderInline(text)}</p>`,
        );
    };

    while (i < lines.length) {
        const line = lines[i];
        const trimmed = line.trim();

        if (!trimmed) {
            i++;
            continue;
        }

        const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
        if (headingMatch) {
            const level = headingMatch[1].length;
            const content = renderInline(headingMatch[2].trim());
            parts.push(`<h${level} class="my-3 font-semibold">${content}</h${level}>`);
            i++;
            continue;
        }

        const ulMatch = line.match(/^\s*[-*+]\s+(.+)$/);
        if (ulMatch) {
            const items = [];
            while (i < lines.length) {
                const m = lines[i].match(/^\s*[-*+]\s+(.+)$/);
                if (!m) break;
                items.push(`<li class="my-1">${renderInline(m[1].trim())}</li>`);
                i++;
            }
            parts.push(`<ul class="my-3 list-disc pl-6">${items.join('')}</ul>`);
            continue;
        }

        const olMatch = line.match(/^\s*\d+\.\s+(.+)$/);
        if (olMatch) {
            const items = [];
            while (i < lines.length) {
                const m = lines[i].match(/^\s*\d+\.\s+(.+)$/);
                if (!m) break;
                items.push(`<li class="my-1">${renderInline(m[1].trim())}</li>`);
                i++;
            }
            parts.push(`<ol class="my-3 list-decimal pl-6">${items.join('')}</ol>`);
            continue;
        }

        const paragraphLines = [];
        while (i < lines.length && lines[i].trim() !== '') {
            const l = lines[i];
            const isNextBlock =
                /^(#{1,6})\s+/.test(l) ||
                /^\s*[-*+]\s+/.test(l) ||
                /^\s*\d+\.\s+/.test(l);
            if (isNextBlock) break;
            paragraphLines.push(l);
            i++;
        }

        flushParagraph(paragraphLines);
    }

    let html = parts.join('');
    html = html.replace(/@@CODEBLOCK_(\d+)@@/g, (match, idx) => {
        const codeIndex = Number(idx);
        return codeBlocks[codeIndex] ?? match;
    });

    return html;
};

const renderedAnswer = computed(() => renderMarkdown(answer.value));
const renderedError = computed(() => (error.value ? renderMarkdown(error.value) : ''));

const ask = async () => {
    error.value = '';
    answer.value = '';

    const trimmed = question.value.trim();
    if (!trimmed) {
        error.value = 'Please enter a question.';
        return;
    }

    loading.value = true;
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: trimmed,
                game: game.value,
            }),
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            error.value = data?.error
                ? `${data.error} (HTTP ${response.status})`
                : `Request failed (HTTP ${response.status}).`;
            return;
        }

        if (typeof data?.answer === 'string') {
            answer.value = data.answer;
        } else if (data?.error) {
            error.value = data.error;
        } else {
            answer.value = '';
            error.value = 'No answer returned.';
        }
    } catch (e) {
        error.value = 'Failed to reach the server.';
    } finally {
        loading.value = false;
    }
};
</script>

<template>

    <Head title="Warhammer Rule Assistant" />

    <AppLayout :breadcrumbs="breadcrumbs">
        <div class="flex h-full flex-1 flex-col gap-4 overflow-x-hidden rounded-xl p-4">
            <div class="space-y-4 rounded-xl border border-sidebar-border/70 bg-sidebar/5 p-4">
                <h1 class="text-lg font-semibold">Question</h1>

                <label class="block text-sm font-medium text-foreground">
                    Your question
                </label>
                <Input v-model="question" class="w-full" placeholder="Ask a Warhammer rules question..."
                    :disabled="loading" />

                <div class="flex items-center justify-between gap-4">
                    <div class="flex flex-col gap-1">
                        <span class="text-sm font-medium text-foreground">
                            Game
                        </span>
                        <div class="flex gap-4">
                            <label class="inline-flex items-center gap-2 text-sm">
                                <input type="radio" name="game" value="aos" v-model="game" :disabled="loading" />
                                <span>Age of Sigmar</span>
                            </label>
                            <label class="inline-flex items-center gap-2 text-sm">
                                <input type="radio" name="game" value="40k" v-model="game" :disabled="loading" />
                                <span>40.000</span>
                            </label>
                        </div>
                    </div>

                    <Button :disabled="loading || !question.trim()" class="h-9 px-4" @click="ask">
                        <span v-if="loading">Asking...</span>
                        <span v-else>Ask</span>
                    </Button>
                </div>
            </div>

            <div class="space-y-2 rounded-xl border border-sidebar-border/70 bg-sidebar/5 p-4">
                <h2 class="text-lg font-semibold">Answer</h2>

                <div class="min-h-[160px] whitespace-pre-wrap rounded-lg p-3 text-sm leading-relaxed text-foreground">
                    <template v-if="renderedError">
                        <div class="my-2 rounded-lg bg-red-50 p-3 text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-100 dark:ring-red-900/40"
                            v-html="renderedError" />
                    </template>

                    <template v-else-if="renderedAnswer">
                        <div v-html="renderedAnswer" />
                    </template>

                    <template v-else>
                        <p class="text-muted-foreground">No answer yet. Ask a question above.</p>
                    </template>
                </div>
            </div>
        </div>
    </AppLayout>
</template>