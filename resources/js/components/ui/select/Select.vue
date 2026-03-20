<script setup lang="js">
import { SelectRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps({
  defaultValue: { default: undefined },
  modelValue: { default: undefined },
  defaultOpen: { type: Boolean, default: false },
  open: { default: undefined },
  dir: { default: undefined },
  name: { default: undefined },
  autocomplete: { default: undefined },
  disabled: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
})
const emits = defineEmits(['update:modelValue', 'update:open'])

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <SelectRoot
    v-slot="slotProps"
    data-slot="select"
    v-bind="forwarded"
  >
    <slot v-bind="slotProps" />
  </SelectRoot>
</template>
