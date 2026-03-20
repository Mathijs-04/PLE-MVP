<script setup lang="js">
import AuthLayout from '@/layouts/auth/AuthSimpleLayout.vue';

defineProps({
    title: { default: undefined },
    description: { default: undefined },
});
</script>

<template>
    <AuthLayout :title="title" :description="description">
        <slot />
    </AuthLayout>
</template>
