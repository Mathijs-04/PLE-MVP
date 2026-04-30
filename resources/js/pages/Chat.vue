<script setup lang="js">
import { Head } from '@inertiajs/vue3';
import { ChevronDown, Moon, Sun } from 'lucide-vue-next';
import {
    computed,
    nextTick,
    onBeforeUnmount,
    onMounted,
    reactive,
    ref,
    watch,
} from 'vue';
import GameBackground from '@/components/GameBackground.vue';
import PrimaryNav from '@/components/PrimaryNav.vue';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAppearance } from '@/composables/useAppearance';
import { getTagsForGame, wrapRuleTagLinks } from '@/utils/ruleTagLinks';

const { resolvedAppearance, updateAppearance } = useAppearance();

const toggleTheme = () => {
    updateAppearance(resolvedAppearance.value === 'dark' ? 'light' : 'dark');
};

const warhammerLogo = computed(() =>
    resolvedAppearance.value === 'light'
        ? '/Warhammer-Light.png'
        : '/Warhammer.png',
);

const CHAT_DRAFT_KEY = 'warhammer_chat_draft_v1';

function isDocumentReloadNavigation() {
    const entry = performance.getEntriesByType?.('navigation')?.[0];

    if (entry && 'type' in entry && entry.type === 'reload') {
        return true;
    }

    if (
        typeof performance.navigation !== 'undefined' &&
        performance.navigation.type === 1
    ) {
        return true;
    }

    return false;
}

function readChatDraft() {
    try {
        const raw = sessionStorage.getItem(CHAT_DRAFT_KEY);

        if (!raw) {
            return null;
        }

        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function writeChatDraft(payload) {
    try {
        sessionStorage.setItem(CHAT_DRAFT_KEY, JSON.stringify(payload));
    } catch {
        void 0;
    }
}

function clearChatDraft() {
    try {
        sessionStorage.removeItem(CHAT_DRAFT_KEY);
    } catch {
        void 0;
    }
}

let skipDraftPersist = false;

const question = ref('');
const questionTextarea = ref(null);
const game = ref('aos');
const loading = ref(false);
const loadingQuestion = ref('');
const error = ref('');
const answers = reactive({ aos: null, '40k': null });
const questions = reactive({ aos: null, '40k': null });
const answer = computed(() => answers[game.value]);

const openShortAnswer = ref(true);
const openDetailedAnswer = ref(false);
const openSource = ref(false);

const armyListStrongPhrases = [
    'army list',
    'army build',
    'army composition',
    'army roster',
    'starter army',
    'starter force',
    'starter list',
    'list building',
    'list-building',
];

const armyListWeakSignals = [
    'army',
    'list',
    'roster',
    'build',
    'building',
    'good',
    'recommend',
    'recommended',
    'suggest',
    'force',
];

const armyListVerbPattern =
    /\b(?:build|make|create|design|recommend|suggest|write|give|draft|put\s+together)(?:\s+(?:me|us|a|an|the))*(?:\s+\w+){0,6}?\s+(?:army|list|roster|force)\b/i;

function hasPointsBudget(value) {
    const q = value.toLowerCase();

    return (
        /(\d[\d,]{2,5})\s*[-\s]?\s*(?:point|points|pts|pt)\b/.test(q) ||
        /\b(\d(?:\.\d)?)\s*k\s*(?:point|points|pts|pt)?\b/.test(q) ||
        /\b(?:for|at|of|with|around|about)\s+(\d[\d,]{2,5})\b/.test(q)
    );
}

function isArmyQuestionText(value) {
    const q = value.toLowerCase();
    const strong =
        armyListStrongPhrases.some((phrase) => q.includes(phrase)) ||
        armyListVerbPattern.test(value);
    const weak = armyListWeakSignals.some((signal) => q.includes(signal));

    return strong || (hasPointsBudget(value) && weak);
}

const loadingText = computed(() =>
    isArmyQuestionText(loadingQuestion.value)
        ? 'Building an army...'
        : 'Searching the rules…',
);

function resizeQuestionTextarea() {
    const el = questionTextarea.value;

    if (!el) {
        return;
    }

    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

function submitQuestionFromTextarea(event) {
    if (event.shiftKey) {
        return;
    }

    event.preventDefault();
    ask();
}

onMounted(async () => {
    document.documentElement.classList.remove('overflow-y-hidden');
    document.body.classList.remove('overflow-y-hidden');
    window.addEventListener('resize', resizeQuestionTextarea);

    await nextTick();
    resizeQuestionTextarea();

    if (isDocumentReloadNavigation()) {
        clearChatDraft();

        return;
    }

    const draft = readChatDraft();

    if (!draft || typeof draft !== 'object') {
        return;
    }

    skipDraftPersist = true;

    if (typeof draft.question === 'string') {
        question.value = draft.question;
    }

    if (draft.game === '40k' || draft.game === 'aos') {
        game.value = draft.game;
    }

    if (draft.answers && typeof draft.answers === 'object') {
        if (
            draft.answers.aos &&
            typeof draft.answers.aos.short_answer === 'string'
        ) {
            answers.aos = draft.answers.aos;
        }

        if (
            draft.answers['40k'] &&
            typeof draft.answers['40k'].short_answer === 'string'
        ) {
            answers['40k'] = draft.answers['40k'];
        }
    } else if (
        draft.answer &&
        typeof draft.answer === 'object' &&
        typeof draft.answer.short_answer === 'string' &&
        typeof draft.answer.detailed_answer === 'string'
    ) {
        answers[draft.game === '40k' ? '40k' : 'aos'] = draft.answer;
    }

    if (draft.questions && typeof draft.questions === 'object') {
        if (typeof draft.questions.aos === 'string') {
            questions.aos = draft.questions.aos;
        }

        if (typeof draft.questions['40k'] === 'string') {
            questions['40k'] = draft.questions['40k'];
        }
    }

    if (typeof draft.openShortAnswer === 'boolean') {
        openShortAnswer.value = draft.openShortAnswer;
    }

    if (typeof draft.openDetailedAnswer === 'boolean') {
        openDetailedAnswer.value = draft.openDetailedAnswer;
    }

    if (typeof draft.openSource === 'boolean') {
        openSource.value = draft.openSource;
    }

    await nextTick();
    resizeQuestionTextarea();
    skipDraftPersist = false;
});

onBeforeUnmount(() => {
    window.removeEventListener('resize', resizeQuestionTextarea);
});

watch(question, async () => {
    await nextTick();
    resizeQuestionTextarea();
});

watch(
    [
        question,
        game,
        answers,
        questions,
        openShortAnswer,
        openDetailedAnswer,
        openSource,
    ],
    () => {
        if (skipDraftPersist || loading.value) {
            return;
        }

        const q = question.value.trim();

        if (!q && !answers.aos && !answers['40k']) {
            clearChatDraft();

            return;
        }

        writeChatDraft({
            question: question.value,
            game: game.value,
            answers: { aos: answers.aos, '40k': answers['40k'] },
            questions: { aos: questions.aos, '40k': questions['40k'] },
            openShortAnswer: openShortAnswer.value,
            openDetailedAnswer: openDetailedAnswer.value,
            openSource: openSource.value,
        });
    },
    { deep: true },
);

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
    const tokenized = escaped.replace(
        /```(\w+)?\n([\s\S]*?)```/g,
        (match, lang, code) => {
            const i = codeBlocks.length;
            const language = lang ? ` language-${String(lang)}` : '';
            codeBlocks.push(
                `<pre class="my-3 overflow-x-auto rounded-lg bg-sidebar/10 p-3 ring-1 ring-sidebar-border/70"><code class="${language} whitespace-pre">${code}</code></pre>`,
            );

            return `@@CODEBLOCK_${i}@@`;
        },
    );

    const renderInline = (value) => {
        let html = value;

        html = html.replace(
            /`([^`]+)`/g,
            '<code class="rounded bg-sidebar/10 px-1 py-0.5 ring-1 ring-sidebar-border/70">$1</code>',
        );
        html = html.replace(
            /\*\*([^*]+)\*\*/g,
            '<strong class="font-semibold">$1</strong>',
        );
        html = html.replace(
            /(^|[^*])\*([^*]+)\*(?!\*)/g,
            '$1<em class="italic">$2</em>',
        );

        return html;
    };

    const lines = tokenized.split('\n');
    const parts = [];
    let i = 0;

    const flushParagraph = (paragraphLines) => {
        const text = paragraphLines.join('\n').trimEnd();

        if (!text) {
            return;
        }

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
            const sizeClass =
                level === 1 ? 'text-xl' : level === 2 ? 'text-lg' : 'text-base';
            parts.push(
                `<h${level} class="font-title mt-5 mb-2 ${sizeClass} font-bold tracking-[0.03em]">${content}</h${level}>`,
            );
            i++;
            continue;
        }

        const ulMatch = line.match(/^\s*[-*+]\s+(.+)$/);

        if (ulMatch) {
            const items = [];

            while (i < lines.length) {
                const m = lines[i].match(/^\s*[-*+]\s+(.+)$/);

                if (!m) {
                    break;
                }

                items.push(
                    `<li class="my-1">${renderInline(m[1].trim())}</li>`,
                );
                i++;
            }

            parts.push(
                `<ul class="my-3 list-disc pl-6">${items.join('')}</ul>`,
            );
            continue;
        }

        const olMatch = line.match(/^\s*\d+\.\s+(.+)$/);

        if (olMatch) {
            const items = [];

            while (i < lines.length) {
                const m = lines[i].match(/^\s*\d+\.\s+(.+)$/);

                if (!m) {
                    break;
                }

                items.push(
                    `<li class="my-1">${renderInline(m[1].trim())}</li>`,
                );
                i++;
            }

            parts.push(
                `<ol class="my-3 list-decimal pl-6">${items.join('')}</ol>`,
            );
            continue;
        }

        const paragraphLines = [];

        while (i < lines.length && lines[i].trim() !== '') {
            const l = lines[i];
            const isNextBlock =
                /^(#{1,6})\s+/.test(l) ||
                /^\s*[-*+]\s+/.test(l) ||
                /^\s*\d+\.\s+/.test(l);

            if (isNextBlock) {
                break;
            }

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

const baseDetailedHtml = computed(() =>
    answer.value ? renderMarkdown(answer.value.detailed_answer) : '',
);

const renderedDetailedAnswer = ref('');

watch(
    [baseDetailedHtml, game],
    () => {
        const base = baseDetailedHtml.value;

        if (!base) {
            renderedDetailedAnswer.value = '';

            return;
        }

        renderedDetailedAnswer.value = wrapRuleTagLinks(
            base,
            game.value,
            getTagsForGame(game.value),
        );
    },
    { immediate: true },
);

const certaintyConfig = {
    1: {
        color: 'bg-green-500',
        label: 'High confidence: Answer is directly supported by the rules.',
    },
    2: {
        color: 'bg-yellow-400',
        label: 'Moderate confidence: Answer is partially in the rules and requires some interpretation.',
    },
    3: {
        color: 'bg-orange-500',
        label: 'Low confidence: The rules barely cover this, or may contradict.',
    },
    4: {
        color: 'bg-red-500',
        label: 'Very low confidence: The rules do not cover this, treat with caution.',
    },
};

const certaintyLevel = computed(() => {
    const raw = answer.value?.certainty;

    if (raw >= 1 && raw <= 4) {
        return raw;
    }

    return 4;
});

const formatSource = (source) => {
    if (!source || !String(source).trim()) {
        return 'No relevant source';
    }

    const parts = String(source).split(' & ');

    if (parts.length <= 2) {
        return String(source);
    }

    return parts.slice(0, -1).join(', ') + ' & ' + parts[parts.length - 1];
};

const switchGame = (newGame) => {
    if (answers[newGame]) {
        question.value = questions[newGame] ?? '';
    } else if (answers[game.value]) {
        question.value = '';
    }

    game.value = newGame;
};

const clear = () => {
    questions[game.value] = null;
    answers[game.value] = null;
    question.value = '';
    error.value = '';
};

const ask = async () => {
    error.value = '';
    answers[game.value] = null;

    const trimmed = question.value.trim();

    if (!trimmed) {
        error.value = 'Please enter a question.';

        return;
    }

    loading.value = true;
    loadingQuestion.value = trimmed;

    const askedGame = game.value;

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: trimmed,
                game: askedGame,
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
            answers[askedGame] = data;
            questions[askedGame] = trimmed;
            openShortAnswer.value = true;
            openDetailedAnswer.value = false;
            openSource.value = false;
        } else if (data?.error) {
            error.value = data.error;
        } else {
            answers[askedGame] = null;
            error.value = 'No answer returned.';
        }
    } catch (e) {
        error.value = 'Failed to reach the server.';
    } finally {
        loading.value = false;
    }

    await nextTick();
};
</script>

<template>
    <Head title="Warhammer Rule Assistant" />

    <div class="relative min-h-screen bg-background text-foreground">
        <GameBackground :game="game" />

        <PrimaryNav />

        <button
            type="button"
            class="fixed top-4 right-4 z-50 flex h-9 w-9 items-center justify-center rounded-full border border-sidebar-border/70 bg-sidebar/80 text-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-sidebar"
            :aria-label="
                resolvedAppearance === 'dark'
                    ? 'Switch to light mode'
                    : 'Switch to dark mode'
            "
            @click="toggleTheme"
        >
            <Sun v-if="resolvedAppearance === 'dark'" class="h-4 w-4" />
            <Moon v-else class="h-4 w-4" />
        </button>

        <div
            class="relative z-10 mx-auto max-w-3xl space-y-6 px-4 pt-16 pb-10 sm:pt-[68px]"
        >
            <div
                class="space-y-5 rounded-xl border border-sidebar-border/70 bg-sidebar/5 p-6"
            >
                <div class="flex items-start justify-between gap-4">
                    <div class="min-w-0 flex-1">
                        <h1
                            class="font-title text-lg font-bold tracking-[0.03em] sm:text-2xl"
                        >
                            Warhammer Rule Assistant
                        </h1>
                        <p
                            class="mt-1 text-xs text-muted-foreground sm:text-sm"
                        >
                            Ask any rule-related question and get an answer
                            based on the official rules.
                        </p>
                    </div>
                    <img
                        :src="warhammerLogo"
                        alt="Warhammer"
                        class="h-14 w-14 shrink-0 object-contain sm:h-16 sm:w-16"
                        width="64"
                        height="64"
                        decoding="async"
                    />
                </div>

                <div class="space-y-1.5">
                    <label class="text-sm font-medium text-foreground"
                        >Your question</label
                    >
                    <Input
                        v-model="question"
                        class="w-full sm:hidden"
                        placeholder="Ask your question..."
                        :disabled="loading"
                        @keyup.enter="ask"
                    />
                    <textarea
                        ref="questionTextarea"
                        v-model="question"
                        rows="1"
                        wrap="soft"
                        class="question-textarea hidden max-h-40 min-h-9 w-full min-w-0 resize-none overflow-y-auto rounded-md border border-input bg-transparent px-3 py-1 text-base leading-[26px] shadow-xs transition-[color,box-shadow] outline-none selection:bg-primary selection:text-primary-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 sm:block md:text-sm dark:bg-input/30 dark:aria-invalid:ring-destructive/40"
                        placeholder="Ask your question..."
                        :disabled="loading"
                        @input="resizeQuestionTextarea"
                        @keydown.enter="submitQuestionFromTextarea"
                    />
                </div>

                <div class="flex items-center justify-between gap-4">
                    <div class="flex items-center gap-3">
                        <span
                            class="text-sm transition-colors"
                            :class="
                                game === 'aos'
                                    ? 'font-semibold text-foreground'
                                    : 'text-muted-foreground'
                            "
                            ><span class="sm:hidden">AOS</span
                            ><span class="hidden sm:inline"
                                >Warhammer Age of Sigmar</span
                            ></span
                        >

                        <button
                            type="button"
                            role="switch"
                            :aria-checked="game === '40k'"
                            :disabled="loading"
                            class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                            :class="game === '40k' ? 'bg-primary' : 'bg-input'"
                            @click="switchGame(game === 'aos' ? '40k' : 'aos')"
                        >
                            <span
                                class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow-lg ring-0 transition-transform"
                                :class="
                                    game === '40k'
                                        ? 'translate-x-5'
                                        : 'translate-x-0'
                                "
                            />
                        </button>

                        <span
                            class="text-sm transition-colors"
                            :class="
                                game === '40k'
                                    ? 'font-semibold text-foreground'
                                    : 'text-muted-foreground'
                            "
                            ><span class="sm:hidden">40K</span
                            ><span class="hidden sm:inline"
                                >Warhammer 40.000</span
                            ></span
                        >
                    </div>

                    <div class="flex items-center gap-2">
                        <Button
                            variant="outline"
                            :disabled="loading || !answer"
                            class="h-9 px-5"
                            @click="clear"
                        >
                            Clear
                        </Button>
                        <Button
                            :disabled="loading || !question.trim()"
                            class="h-9 px-5"
                            @click="ask"
                        >
                            <span v-if="loading">Asking…</span>
                            <span v-else>Ask</span>
                        </Button>
                    </div>
                </div>
            </div>

            <div
                class="rounded-xl border border-sidebar-border/70 bg-sidebar/5 p-6"
            >
                <template v-if="error">
                    <div
                        class="rounded-lg bg-red-50 p-4 text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-100 dark:ring-red-900/40"
                    >
                        {{ error }}
                    </div>
                </template>

                <template v-else-if="answer">
                    <div class="space-y-3">
                        <div
                            class="relative z-20 rounded-lg border border-sidebar-border/70"
                        >
                            <button
                                type="button"
                                class="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-sidebar/10"
                                @click="openShortAnswer = !openShortAnswer"
                            >
                                <span
                                    class="font-title text-xs font-semibold tracking-widest text-muted-foreground uppercase"
                                    >Short Answer</span
                                >
                                <ChevronDown
                                    class="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200"
                                    :class="openShortAnswer ? 'rotate-180' : ''"
                                />
                            </button>
                            <div
                                v-show="openShortAnswer"
                                class="border-t border-sidebar-border/70 bg-sidebar/10 px-4 py-4"
                            >
                                <div
                                    class="flex items-start justify-between gap-3"
                                >
                                    <p
                                        class="text-base leading-snug font-bold sm:text-xl"
                                    >
                                        {{ answer.short_answer }}
                                    </p>
                                    <span class="group relative mt-1 shrink-0">
                                        <span
                                            class="block h-3 w-3 rounded-full"
                                            :class="
                                                certaintyConfig[certaintyLevel]
                                                    .color
                                            "
                                        />
                                        <span
                                            class="pointer-events-none absolute right-0 bottom-full z-50 mb-2 w-56 rounded-lg bg-popover px-3 py-2 text-xs leading-snug text-popover-foreground opacity-0 shadow-lg ring-1 ring-sidebar-border/70 transition-opacity group-hover:opacity-100"
                                        >
                                            {{
                                                certaintyConfig[certaintyLevel]
                                                    .label
                                            }}
                                        </span>
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div
                            class="overflow-hidden rounded-lg border border-sidebar-border/70"
                        >
                            <button
                                type="button"
                                class="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-sidebar/10"
                                @click="
                                    openDetailedAnswer = !openDetailedAnswer
                                "
                            >
                                <span
                                    class="font-title text-xs font-semibold tracking-widest text-muted-foreground uppercase"
                                    >Detailed Answer</span
                                >
                                <ChevronDown
                                    class="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200"
                                    :class="
                                        openDetailedAnswer ? 'rotate-180' : ''
                                    "
                                />
                            </button>
                            <div
                                v-show="openDetailedAnswer"
                                class="border-t border-sidebar-border/70 px-4 py-4 text-sm leading-relaxed"
                            >
                                <div v-html="renderedDetailedAnswer" />
                            </div>
                        </div>

                        <div
                            class="overflow-hidden rounded-lg border border-sidebar-border/70"
                        >
                            <button
                                type="button"
                                class="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-sidebar/10"
                                @click="openSource = !openSource"
                            >
                                <span
                                    class="font-title text-xs font-semibold tracking-widest text-muted-foreground uppercase"
                                    >Source</span
                                >
                                <ChevronDown
                                    class="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200"
                                    :class="openSource ? 'rotate-180' : ''"
                                />
                            </button>
                            <div
                                v-show="openSource"
                                class="border-t border-sidebar-border/70 bg-sidebar/10 px-4 py-4"
                            >
                                <p class="text-sm text-muted-foreground">
                                    {{ formatSource(answer.source) }}
                                </p>
                            </div>
                        </div>
                    </div>
                </template>

                <template v-else-if="loading">
                    <div
                        class="flex flex-col items-center justify-center gap-3 py-12 text-muted-foreground"
                    >
                        <svg
                            class="h-8 w-8 animate-spin text-primary"
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                        >
                            <circle
                                class="opacity-25"
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                stroke-width="4"
                            />
                            <path
                                class="opacity-75"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                            />
                        </svg>
                        <span class="text-sm">{{ loadingText }}</span>
                    </div>
                </template>

                <template v-else>
                    <p class="py-4 text-center text-sm text-muted-foreground">
                        Ask a question to get an answer.
                    </p>
                </template>
            </div>
        </div>
    </div>
</template>

<style scoped>
.question-textarea {
    scrollbar-width: none;
    -ms-overflow-style: none;
}

.question-textarea::-webkit-scrollbar {
    display: none;
}
</style>
