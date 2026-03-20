<script setup lang="js">
import { reactiveOmit } from "@vueuse/core"
import { useForwardPropsEmits } from "reka-ui"
import { OTPInput } from "vue-input-otp"
import { cn } from "@/lib/utils"

const props = defineProps({
  modelValue: { default: undefined },
  maxlength: { default: undefined },
  disabled: { type: Boolean, default: false },
  autofocus: { type: Boolean, default: false },
  pushPasswordManagerStrategy: { default: undefined },
  pasteTransformer: { default: undefined },
  containerClass: { default: undefined },
  class: { default: undefined },
})

const emits = defineEmits(['update:modelValue', 'complete'])

const delegatedProps = reactiveOmit(props, "class")

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <OTPInput
    v-slot="slotProps"
    v-bind="forwarded"
    :container-class="cn('flex items-center gap-2 has-disabled:opacity-50', props.class)"
    data-slot="input-otp"
    class="disabled:cursor-not-allowed"
  >
    <slot v-bind="slotProps" />
  </OTPInput>
</template>
