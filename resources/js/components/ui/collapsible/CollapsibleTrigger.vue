<script setup lang="js">
import { CollapsibleTrigger } from "reka-ui"

const props = defineProps({
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
})
</script>

<template>
  <CollapsibleTrigger
    data-slot="collapsible-trigger"
    v-bind="props"
  >
    <slot />
  </CollapsibleTrigger>
</template>
