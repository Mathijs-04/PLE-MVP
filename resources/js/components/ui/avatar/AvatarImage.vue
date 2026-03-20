<script setup lang="js">
import { AvatarImage } from "reka-ui"

const props = defineProps({
  src: { default: undefined },
  alt: { default: undefined },
  referrerpolicy: { default: undefined },
  crossorigin: { default: undefined },
})
</script>

<template>
  <AvatarImage
    data-slot="avatar-image"
    v-bind="props"
    class="aspect-square size-full"
  >
    <slot />
  </AvatarImage>
</template>
