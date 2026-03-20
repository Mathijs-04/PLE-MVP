<script setup lang="js">
import { DropdownMenuRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps({
  defaultOpen: { type: Boolean, default: false },
  open: { default: undefined },
  dir: { default: undefined },
  modal: { type: Boolean, default: true },
})
const emits = defineEmits(['update:open'])

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <DropdownMenuRoot
    v-slot="slotProps"
    data-slot="dropdown-menu"
    v-bind="forwarded"
  >
    <slot v-bind="slotProps" />
  </DropdownMenuRoot>
</template>
