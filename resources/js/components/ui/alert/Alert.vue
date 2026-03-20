<script setup lang="js">
import { cn } from "@/lib/utils"
import { alertVariants } from "."

const props = defineProps({
  class: { default: undefined },
  variant: { default: undefined },
})
</script>

<template>
  <div
    data-slot="alert"
    :class="cn(alertVariants({ variant }), props.class)"
    role="alert"
  >
    <slot />
  </div>
</template>
