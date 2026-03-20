<script setup lang="js">
import { SelectValue } from "reka-ui"

const props = defineProps({
  placeholder: { default: undefined },
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
})
</script>

<template>
  <SelectValue
    data-slot="select-value"
    v-bind="props"
  >
    <slot />
  </SelectValue>
</template>
