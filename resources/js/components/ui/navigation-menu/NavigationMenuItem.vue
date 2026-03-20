<script setup lang="js">
import { reactiveOmit } from "@vueuse/core"
import { NavigationMenuItem } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps({
  value: { default: undefined },
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
  class: { default: undefined },
})

const delegatedProps = reactiveOmit(props, "class")
</script>

<template>
  <NavigationMenuItem
    data-slot="navigation-menu-item"
    v-bind="delegatedProps"
    :class="cn('relative', props.class)"
  >
    <slot />
  </NavigationMenuItem>
</template>
