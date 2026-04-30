<script setup lang="js">
import { Head, Link, router, usePage } from '@inertiajs/vue3';
import { ArrowLeft, Moon, Sun } from 'lucide-vue-next';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import GameBackground from '@/components/GameBackground.vue';
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
let mobileViewerMediaQuery = null;

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
    const hash = `#page=${pdfPage.value}&zoom=${zoom}`;

    return `/pdfjs/web/viewer.html?file=${file}${hash}`;
});

const iframeKey = computed(
    () => `${game.value}-${pdfPage.value}-${isMobileViewer.value}`,
);

function updateMobileViewerFlag() {
    isMobileViewer.value = mobileViewerMediaQuery?.matches ?? false;
}

function toggleGame() {
    const next = game.value === 'aos' ? '40k' : 'aos';
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
});

onBeforeUnmount(() => {
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
                                    class="font-title text-lg font-bold tracking-[0.03em] sm:text-2xl"
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
                                class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
                                :class="
                                    game === '40k' ? 'bg-primary' : 'bg-input'
                                "
                                @click="toggleGame"
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
                    </div>
                </div>
            </div>

            <div class="mx-auto flex w-full max-w-5xl justify-center px-4">
                <iframe
                    :key="iframeKey"
                    :src="viewerSrc"
                    class="rounded-xl border border-sidebar-border/70"
                    :style="{
                        width: 'min(735px, 100%)',
                        height: 'min(1122px, calc(100vh - 240px))',
                    }"
                    allowfullscreen
                />
            </div>
        </div>
    </div>
</template>
