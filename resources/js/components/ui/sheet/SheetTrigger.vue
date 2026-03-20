<script setup lang="js">
import { DialogTrigger } from "reka-ui"

const props = defineProps({
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
})
</script>

<template>
  <DialogTrigger
    data-slot="sheet-trigger"
    v-bind="props"
  >
    <slot />
  </DialogTrigger>
</template>
