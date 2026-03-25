<script setup lang="js">
import { computed, ref } from 'vue';
import { Head, Link } from '@inertiajs/vue3';
import { ChevronDown } from 'lucide-vue-next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const question = ref('');
const game = ref('aos');
const loading = ref(false);
const error = ref('');
const answer = ref(null);

const openShortAnswer = ref(true);
const openDetailedAnswer = ref(true);
const openSource = ref(true);

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
            const sizeClass = level === 1 ? 'text-xl' : level === 2 ? 'text-lg' : 'text-base';
            parts.push(`<h${level} class="mt-5 mb-2 ${sizeClass} font-bold tracking-tight">${content}</h${level}>`);
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

const renderedDetailedAnswer = computed(() => (answer.value ? renderMarkdown(answer.value.detailed_answer) : ''));

const ask = async () => {
    error.value = '';
    answer.value = null;

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

        if (data?.short_answer !== undefined) {
            answer.value = data;
            openShortAnswer.value = true;
            openDetailedAnswer.value = true;
            openSource.value = true;
        } else if (data?.error) {
            error.value = data.error;
        } else {
            answer.value = null;
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

    <div class="min-h-screen bg-background text-foreground">
        <div class="mx-auto max-w-3xl space-y-6 px-4 py-10">

            <div class="space-y-5 rounded-xl border border-sidebar-border/70 bg-sidebar/5 p-6">
                <div class="flex items-start justify-between gap-4">
                    <div class="min-w-0 flex-1">
                        <h1 class="text-2xl font-bold tracking-tight">Warhammer Rule Assistant</h1>
                        <p class="mt-1 text-sm text-muted-foreground">Ask any rules question and get an answer based on the official rulebooks.</p>
                    </div>
                    <Link href="/rules" class="inline-flex shrink-0">
                        <img
                            src="/Warhammer.png"
                            alt="Warhammer"
                            class="h-14 w-14 shrink-0 object-contain sm:h-16 sm:w-16"
                            width="64"
                            height="64"
                            decoding="async"
                        />
                    </Link>
                </div>

                <div class="space-y-1.5">
                    <label class="text-sm font-medium text-foreground">Your question</label>
                    <Input
                        v-model="question"
                        class="w-full"
                        placeholder="Ask a Warhammer rules question..."
                        :disabled="loading"
                        @keyup.enter="ask"
                    />
                </div>

                <div class="flex items-center justify-between gap-4">
                    <div class="flex items-center gap-3">
                        <span
                            class="text-sm transition-colors"
                            :class="game === 'aos' ? 'font-semibold text-foreground' : 'text-muted-foreground'"
                        >Warhammer Age of Sigmar</span>

                        <button
                            type="button"
                            role="switch"
                            :aria-checked="game === '40k'"
                            :disabled="loading"
                            class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            :class="game === '40k' ? 'bg-primary' : 'bg-input'"
                            @click="game = game === 'aos' ? '40k' : 'aos'"
                        >
                            <span
                                class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow-lg ring-0 transition-transform"
                                :class="game === '40k' ? 'translate-x-5' : 'translate-x-0'"
                            />
                        </button>

                        <span
                            class="text-sm transition-colors"
                            :class="game === '40k' ? 'font-semibold text-foreground' : 'text-muted-foreground'"
                        >Warhammer 40.000</span>
                    </div>

                    <Button :disabled="loading || !question.trim()" class="h-9 px-5" @click="ask">
                        <span v-if="loading">Asking…</span>
                        <span v-else>Ask</span>
                    </Button>
                </div>
            </div>

            <div class="rounded-xl border border-sidebar-border/70 bg-sidebar/5 p-6">

                <template v-if="error">
                    <div class="rounded-lg bg-red-50 p-4 text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-100 dark:ring-red-900/40">
                        {{ error }}
                    </div>
                </template>

                <template v-else-if="loading">
                    <div class="flex flex-col items-center justify-center gap-3 py-12 text-muted-foreground">
                        <svg class="h-8 w-8 animate-spin text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        <span class="text-sm">Looking up the rules…</span>
                    </div>
                </template>

                <template v-else-if="answer">
                    <div class="space-y-3">

                        <div class="overflow-hidden rounded-lg border border-sidebar-border/70">
                            <button
                                type="button"
                                class="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-sidebar/10 transition-colors"
                                @click="openShortAnswer = !openShortAnswer"
                            >
                                <span class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Short Answer</span>
                                <ChevronDown class="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200" :class="openShortAnswer ? 'rotate-180' : ''" />
                            </button>
                            <div v-show="openShortAnswer" class="border-t border-sidebar-border/70 bg-sidebar/10 px-4 py-4">
                                <p class="text-xl font-bold leading-snug">{{ answer.short_answer }}</p>
                            </div>
                        </div>

                        <div class="overflow-hidden rounded-lg border border-sidebar-border/70">
                            <button
                                type="button"
                                class="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-sidebar/10 transition-colors"
                                @click="openDetailedAnswer = !openDetailedAnswer"
                            >
                                <span class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Detailed Answer</span>
                                <ChevronDown class="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200" :class="openDetailedAnswer ? 'rotate-180' : ''" />
                            </button>
                            <div v-show="openDetailedAnswer" class="border-t border-sidebar-border/70 px-4 py-4 text-sm leading-relaxed">
                                <div v-html="renderedDetailedAnswer" />
                            </div>
                        </div>

                        <div class="overflow-hidden rounded-lg border border-sidebar-border/70">
                            <button
                                type="button"
                                class="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-sidebar/10 transition-colors"
                                @click="openSource = !openSource"
                            >
                                <span class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Source</span>
                                <ChevronDown class="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200" :class="openSource ? 'rotate-180' : ''" />
                            </button>
                            <div v-show="openSource" class="border-t border-sidebar-border/70 bg-sidebar/10 px-4 py-4">
                                <p class="text-sm text-muted-foreground">{{ answer.source }}</p>
                            </div>
                        </div>

                    </div>
                </template>

                <template v-else>
                    <p class="py-4 text-center text-sm text-muted-foreground">No answer yet. Ask a question above.</p>
                </template>

            </div>
        </div>
    </div>
</template>
