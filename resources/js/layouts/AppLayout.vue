<script setup lang="js">
import AppLayout from '@/layouts/app/AppSidebarLayout.vue';

defineProps({
    breadcrumbs: { default: () => [] },
});
</script>

<template>
    <AppLayout :breadcrumbs="breadcrumbs">
        <slot />
    </AppLayout>
</template>
