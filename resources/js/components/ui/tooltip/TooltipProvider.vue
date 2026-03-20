<script setup lang="js">
import { TooltipProvider } from "reka-ui"

const props = defineProps({
  delayDuration: { default: 0 },
  skipDelayDuration: { default: undefined },
  disableHoverableContent: { type: Boolean, default: undefined },
  disableClosingTrigger: { type: Boolean, default: undefined },
  disabled: { type: Boolean, default: undefined },
  ignoreNonKeyboardFocus: { type: Boolean, default: undefined },
})
</script>

<template>
  <TooltipProvider v-bind="props">
    <slot />
  </TooltipProvider>
</template>
