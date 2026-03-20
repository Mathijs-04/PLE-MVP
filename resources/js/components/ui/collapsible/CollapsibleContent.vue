<script setup lang="js">
import { CollapsibleContent } from "reka-ui"

const props = defineProps({
  forceMount: { default: undefined },
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
})
</script>

<template>
  <CollapsibleContent
    data-slot="collapsible-content"
    v-bind="props"
  >
    <slot />
  </CollapsibleContent>
</template>
