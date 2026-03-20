<script setup lang="js">
import { TooltipTrigger } from "reka-ui"

const props = defineProps({
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
})
</script>

<template>
  <TooltipTrigger
    data-slot="tooltip-trigger"
    v-bind="props"
  >
    <slot />
  </TooltipTrigger>
</template>
