<script setup lang="js">
import { Head, Link, router, usePage } from '@inertiajs/vue3';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const rulesOverflowClass = 'overflow-y-hidden';

const inertiaPage = usePage();

const game = ref('aos');
const pdfPage = ref(1);

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
}

watch(() => inertiaPage.url, parseUrl, { immediate: true });

const viewerSrc = computed(() => {
    const file = encodeURIComponent(pdfFiles[game.value]);
    const hash = `#page=${pdfPage.value}`;

    return `/pdfjs/web/viewer.html?file=${file}&zoom=FitH${hash}`;
});

const iframeKey = computed(() => `${game.value}-${pdfPage.value}`);

function toggleGame() {
    const next = game.value === 'aos' ? '40k' : 'aos';
    router.get(
        '/rules',
        { game: next, page: 1 },
        { preserveState: true, replace: true },
    );
}

onMounted(() => {
    document.documentElement.classList.add(rulesOverflowClass);
    document.body.classList.add(rulesOverflowClass);
});

onBeforeUnmount(() => {
    document.documentElement.classList.remove(rulesOverflowClass);
    document.body.classList.remove(rulesOverflowClass);
});
</script>

<template>
    <Head title="Core Rules" />

    <div class="min-h-screen bg-background text-foreground">
        <div class="space-y-6 py-10">

            <div class="mx-auto max-w-3xl px-4">
                <div class="space-y-5 rounded-xl border border-sidebar-border/70 bg-sidebar/5 p-6">
                    <div class="flex items-start justify-between gap-4">
                        <div class="min-w-0 flex-1">
                            <h1 class="text-2xl font-bold tracking-tight">Warhammer Core Rules</h1>
                            <p class="mt-1 text-sm text-muted-foreground">Browse the official core rulebooks for Age of Sigmar and 40.000.</p>
                        </div>
                        <Link href="/" class="inline-flex shrink-0">
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

                    <div class="flex items-center gap-3">
                        <span
                            class="text-sm transition-colors"
                            :class="game === 'aos' ? 'font-semibold text-foreground' : 'text-muted-foreground'"
                        >Warhammer Age of Sigmar</span>

                        <button
                            type="button"
                            role="switch"
                            :aria-checked="game === '40k'"
                            class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                            :class="game === '40k' ? 'bg-primary' : 'bg-input'"
                            @click="toggleGame"
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
