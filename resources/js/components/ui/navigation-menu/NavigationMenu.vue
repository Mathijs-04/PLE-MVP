<script setup lang="js">
import { reactiveOmit } from "@vueuse/core"
import {
  NavigationMenuRoot,
  useForwardPropsEmits,
} from "reka-ui"
import { cn } from "@/lib/utils"
import NavigationMenuViewport from "./NavigationMenuViewport.vue"

const props = defineProps({
  modelValue: { default: undefined },
  defaultValue: { default: undefined },
  dir: { default: undefined },
  orientation: { default: undefined },
  delayDuration: { default: undefined },
  skipDelayDuration: { default: undefined },
  disableClickTrigger: { default: undefined },
  disableHoverTrigger: { default: undefined },
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
  class: { default: undefined },
  viewport: { type: Boolean, default: true },
})
const emits = defineEmits(['update:modelValue'])

const delegatedProps = reactiveOmit(props, "class", "viewport")
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <NavigationMenuRoot
    v-slot="slotProps"
    data-slot="navigation-menu"
    :data-viewport="viewport"
    v-bind="forwarded"
    :class="cn('group/navigation-menu relative flex max-w-max flex-1 items-center justify-center', props.class)"
  >
    <slot v-bind="slotProps" />
    <NavigationMenuViewport v-if="viewport" />
  </NavigationMenuRoot>
</template>
