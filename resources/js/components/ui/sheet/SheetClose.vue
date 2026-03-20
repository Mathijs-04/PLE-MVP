<script setup lang="js">
import { DialogClose } from "reka-ui"

const props = defineProps({
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
})
</script>

<template>
  <DialogClose
    data-slot="sheet-close"
    v-bind="props"
  >
    <slot />
  </DialogClose>
</template>
