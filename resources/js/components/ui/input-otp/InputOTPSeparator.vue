<script setup lang="js">
import { MinusIcon } from "lucide-vue-next"
import { useForwardProps } from "reka-ui"

const props = defineProps({
  class: { default: undefined },
})

const forwarded = useForwardProps(props)
</script>

<template>
  <div
    data-slot="input-otp-separator"
    role="separator"
    v-bind="forwarded"
  >
    <slot>
      <MinusIcon />
    </slot>
  </div>
</template>
