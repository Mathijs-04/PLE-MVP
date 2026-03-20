<script setup lang="js">
import { DialogRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps({
  defaultOpen: { type: Boolean, default: false },
  open: { default: undefined },
  modal: { type: Boolean, default: true },
})
const emits = defineEmits(['update:open'])

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <DialogRoot
    v-slot="slotProps"
    data-slot="dialog"
    v-bind="forwarded"
  >
    <slot v-bind="slotProps" />
  </DialogRoot>
</template>
