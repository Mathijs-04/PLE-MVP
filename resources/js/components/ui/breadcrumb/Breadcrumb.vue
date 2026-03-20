<script lang="js" setup>
const props = defineProps({
  class: { default: undefined },
})
</script>

<template>
  <nav
    aria-label="breadcrumb"
    data-slot="breadcrumb"
    :class="props.class"
  >
    <slot />
  </nav>
</template>
