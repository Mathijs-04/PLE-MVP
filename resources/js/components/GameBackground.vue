<script setup lang="js">
import { computed } from 'vue';
import { useAppearance } from '@/composables/useAppearance';

const props = defineProps({
    game: {
        type: String,
        required: true,
    },
});

const { resolvedAppearance } = useAppearance();

const backgroundImage = computed(() => {
    const isLight = resolvedAppearance.value === 'light';

    if (props.game === '40k') {
        return `url('${isLight ? '/40K-Background-Light.png' : '/40K-Background.png'}')`;
    }

    return `url('${isLight ? '/AOS-Background-Light.png' : '/AOS-Background.png'}')`;
});
</script>

<template>
    <div
        aria-hidden="true"
        class="pointer-events-none fixed inset-0 z-0 bg-background bg-cover bg-bottom bg-no-repeat"
        :style="{ backgroundImage }"
    />
</template>
