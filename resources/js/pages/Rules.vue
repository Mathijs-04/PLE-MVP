<script setup lang="js">
import { Head, Link, router, usePage } from '@inertiajs/vue3';
import { ArrowLeft, Moon, Sun } from 'lucide-vue-next';
import {
    computed,
    nextTick,
    onBeforeUnmount,
    onMounted,
    ref,
    watch,
} from 'vue';
import GameBackground from '@/components/GameBackground.vue';
import GameSelector from '@/components/GameSelector.vue';
import PrimaryNav from '@/components/PrimaryNav.vue';
import { useAppearance } from '@/composables/useAppearance';

const { resolvedAppearance, updateAppearance } = useAppearance();

const toggleTheme = () => {
    updateAppearance(resolvedAppearance.value === 'dark' ? 'light' : 'dark');
};

const rulesOverflowClass = 'overflow-y-hidden';

const inertiaPage = usePage();

const game = ref('aos');
const pdfPage = ref(1);
const fromChat = ref(false);
const isMobileViewer = ref(false);
const deferredViewerSrc = ref('');
const pdfViewerLoaded = ref(false);
let mobileViewerMediaQuery = null;
let viewerMounted = false;
let viewerLoadFrame = null;
let viewerLoadTimeout = null;
let viewerLoadToken = 0;

const pdfFiles = {
    aos: '/rulebooks/AOS_Core_Rules.pdf',
    '40k': '/rulebooks/40K_Core_Rules.pdf',
};

function parseUrl() {
    const path = inertiaPage.url || '';
    const query = path.includes('?') ? path.slice(path.indexOf('?') + 1) : '';
    const params = new URLSearchParams(query);
    const g = params.get('game');
    game.value = g === '40k' || g === 'wh40k' ? '40k' : 'aos';
    const p = parseInt(params.get('page') || '1', 10);
    pdfPage.value = Number.isFinite(p) && p > 0 ? p : 1;
    fromChat.value = params.get('from') === 'chat';
}

watch(() => inertiaPage.url, parseUrl, { immediate: true });

const viewerSrc = computed(() => {
    const file = encodeURIComponent(pdfFiles[game.value]);
    const zoom = isMobileViewer.value ? 'Fit' : 'FitH';
    const hash = `#page=${pdfPage.value}&zoom=${zoom}&disablehistory=true`;

    return `/pdfjs/web/viewer.html?file=${file}${hash}`;
});

const iframeKey = computed(
    () => `${game.value}-${pdfPage.value}-${isMobileViewer.value}`,
);

const showPdfViewerLoader = computed(
    () => !deferredViewerSrc.value || !pdfViewerLoaded.value,
);

function updateMobileViewerFlag() {
    isMobileViewer.value = mobileViewerMediaQuery?.matches ?? false;
}

function clearViewerLoadSchedule() {
    if (viewerLoadFrame !== null) {
        window.cancelAnimationFrame(viewerLoadFrame);
        viewerLoadFrame = null;
    }

    if (viewerLoadTimeout !== null) {
        window.clearTimeout(viewerLoadTimeout);
        viewerLoadTimeout = null;
    }
}

async function scheduleViewerLoad(src = viewerSrc.value) {
    if (!viewerMounted) {
        return;
    }

    const token = ++viewerLoadToken;
    clearViewerLoadSchedule();
    pdfViewerLoaded.value = false;
    deferredViewerSrc.value = '';

    await nextTick();

    if (token !== viewerLoadToken || !viewerMounted) {
        return;
    }

    viewerLoadFrame = window.requestAnimationFrame(() => {
        viewerLoadFrame = null;
        viewerLoadTimeout = window.setTimeout(() => {
            viewerLoadTimeout = null;

            if (token === viewerLoadToken && viewerMounted) {
                deferredViewerSrc.value = src;
            }
        }, 0);
    });
}

function markPdfViewerLoaded() {
    pdfViewerLoaded.value = true;
}

watch(viewerSrc, (src) => scheduleViewerLoad(src));

function selectGame(next) {
    if (next === game.value) {
        return;
    }

    const params = { game: next, page: 1 };

    if (fromChat.value) {
        params.from = 'chat';
    }

    router.get('/rules', params, { preserveState: true, replace: true });
}

onMounted(() => {
    document.documentElement.classList.add(rulesOverflowClass);
    document.body.classList.add(rulesOverflowClass);

    mobileViewerMediaQuery = window.matchMedia('(max-width: 639px)');
    updateMobileViewerFlag();
    mobileViewerMediaQuery.addEventListener('change', updateMobileViewerFlag);
    viewerMounted = true;
    scheduleViewerLoad();
});

onBeforeUnmount(() => {
    viewerMounted = false;
    clearViewerLoadSchedule();
    mobileViewerMediaQuery?.removeEventListener(
        'change',
        updateMobileViewerFlag,
    );
    document.documentElement.classList.remove(rulesOverflowClass);
    document.body.classList.remove(rulesOverflowClass);
});
</script>

<template>
    <Head title="Core Rules" />

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

        <div class="relative z-10 space-y-6 pt-16 pb-10 sm:pt-[68px]">
            <div class="mx-auto max-w-3xl px-4">
                <div class="relative">
                    <Link
                        v-if="fromChat"
                        href="/"
                        class="absolute top-6.5 -left-10 flex h-8 w-8 items-center justify-center rounded-full text-foreground opacity-60 transition-opacity hover:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
                    >
                        <ArrowLeft class="h-5 w-5" />
                    </Link>
                    <div
                        class="space-y-5 rounded-xl border border-sidebar-border/70 bg-sidebar/5 p-6"
                    >
                        <div class="flex items-start justify-between gap-4">
                            <div class="min-w-0 flex-1">
                                <h1
                                    class="font-title text-base font-bold tracking-[0.03em] sm:text-2xl"
                                >
                                    Warhammer Core Rules
                                </h1>
                                <p
                                    class="mt-1 text-xs text-muted-foreground sm:text-sm"
                                >
                                    Browse the official core rulebooks for Age
                                    of Sigmar and 40.000.
                                </p>
                            </div>
                            <img
                                src="/Warhammer.png"
                                alt="Warhammer"
                                class="h-14 w-14 shrink-0 object-contain sm:h-16 sm:w-16"
                                width="64"
                                height="64"
                                decoding="async"
                            />
                        </div>

                        <GameSelector
                            class="w-full sm:w-auto"
                            name="rules-game"
                            :model-value="game"
                            @update:model-value="selectGame"
                        />
                    </div>
                </div>
            </div>

            <div class="mx-auto flex w-full max-w-5xl justify-center px-4">
                <div
                    class="relative overflow-hidden rounded-xl border border-sidebar-border/70 bg-sidebar/5"
                    :style="{
                        width: 'min(735px, 100%)',
                        height: 'min(1122px, calc(100vh - 240px))',
                    }"
                    :aria-busy="showPdfViewerLoader"
                >
                    <div
                        v-if="showPdfViewerLoader"
                        class="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-background/80 text-muted-foreground backdrop-blur-sm"
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
                        <span class="text-sm">Loading rulebook viewer…</span>
                    </div>

                    <iframe
                        v-if="deferredViewerSrc"
                        :key="iframeKey"
                        :src="deferredViewerSrc"
                        title="Warhammer core rules PDF viewer"
                        class="block h-full w-full transition-opacity duration-200"
                        :class="pdfViewerLoaded ? 'opacity-100' : 'opacity-0'"
                        allowfullscreen
                        @load="markPdfViewerLoaded"
                    />
                </div>
            </div>
        </div>
    </div>
</template>
