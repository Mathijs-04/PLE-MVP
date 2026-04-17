<script setup lang="js">
import { Link } from '@inertiajs/vue3';
import { computed } from 'vue';
import { useCurrentUrl } from '@/composables/useCurrentUrl';

const { currentUrl } = useCurrentUrl();

const isRules = computed(() => currentUrl.value.startsWith('/rules'));
const toggleHref = computed(() => (isRules.value ? '/' : '/rules'));
const toggleLabel = computed(() =>
    isRules.value ? 'Switch to Questions' : 'Switch to Core Rules',
);
</script>

<template>
    <Link
        :href="toggleHref"
        :aria-label="toggleLabel"
        class="group fixed top-4 left-1/2 z-50 inline-flex -translate-x-1/2 items-center gap-1 rounded-full border border-sidebar-border/70 bg-sidebar/80 p-1 shadow-sm backdrop-blur-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
        <span
            :aria-current="!isRules ? 'page' : undefined"
            class="font-title inline-flex h-7 items-center whitespace-nowrap rounded-full px-2.5 text-[10px] font-semibold uppercase tracking-[0.15em] transition-colors sm:px-3 sm:text-xs sm:tracking-widest"
            :class="!isRules ? 'bg-primary text-primary-foreground' : 'text-muted-foreground group-hover:text-foreground'"
        >
            Questions
        </span>
        <span
            :aria-current="isRules ? 'page' : undefined"
            class="font-title inline-flex h-7 items-center whitespace-nowrap rounded-full px-2.5 text-[10px] font-semibold uppercase tracking-[0.15em] transition-colors sm:px-3 sm:text-xs sm:tracking-widest"
            :class="isRules ? 'bg-primary text-primary-foreground' : 'text-muted-foreground group-hover:text-foreground'"
        >
            Core Rules
        </span>
    </Link>
</template>
