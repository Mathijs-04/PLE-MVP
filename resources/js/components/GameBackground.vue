<script setup lang="js">
import { computed } from 'vue';

const props = defineProps({
    game: {
        type: String,
        required: true,
    },
});

const backgroundImage = computed(() => {
    const path = props.game === '40k' ? '/40K-Background.png' : '/AOS-Background.png';

    return `url('${path}')`;
});
</script>

<template>
    <div
        aria-hidden="true"
        class="pointer-events-none fixed inset-0 z-0 bg-background bg-cover bg-bottom bg-no-repeat"
        :style="{ backgroundImage }"
    />
</template>
