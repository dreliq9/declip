#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

static int fail(const char *where, VkResult r) {
    fprintf(stderr, "VULKAN_FAIL where=%s code=%d\n", where, (int)r);
    return 2;
}

int main(void) {
    VkApplicationInfo app = {0};
    app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app.pApplicationName = "media-kernel-language-gate";
    app.applicationVersion = VK_MAKE_VERSION(0, 1, 0);
    app.pEngineName = "declip-research";
    app.engineVersion = VK_MAKE_VERSION(0, 1, 0);
    app.apiVersion = VK_API_VERSION_1_1;

    VkInstanceCreateInfo ici = {0};
    ici.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    ici.pApplicationInfo = &app;

    VkInstance instance = VK_NULL_HANDLE;
    VkResult r = vkCreateInstance(&ici, NULL, &instance);
    if (r != VK_SUCCESS) return fail("vkCreateInstance", r);

    uint32_t physical_count = 0;
    r = vkEnumeratePhysicalDevices(instance, &physical_count, NULL);
    if (r != VK_SUCCESS || physical_count == 0) {
        vkDestroyInstance(instance, NULL);
        return fail("vkEnumeratePhysicalDevices(count)", r);
    }
    VkPhysicalDevice *physical = calloc(physical_count, sizeof(*physical));
    if (!physical) { vkDestroyInstance(instance, NULL); return 3; }
    r = vkEnumeratePhysicalDevices(instance, &physical_count, physical);
    if (r != VK_SUCCESS) { free(physical); vkDestroyInstance(instance, NULL); return fail("vkEnumeratePhysicalDevices", r); }
    VkPhysicalDevice pd = physical[0];
    free(physical);

    VkPhysicalDeviceProperties props;
    vkGetPhysicalDeviceProperties(pd, &props);

    uint32_t qcount = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(pd, &qcount, NULL);
    VkQueueFamilyProperties *qprops = calloc(qcount, sizeof(*qprops));
    if (!qprops) { vkDestroyInstance(instance, NULL); return 3; }
    vkGetPhysicalDeviceQueueFamilyProperties(pd, &qcount, qprops);
    uint32_t family = UINT32_MAX;
    for (uint32_t i = 0; i < qcount; ++i) {
        if (qprops[i].queueCount > 0 && (qprops[i].queueFlags & (VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT))) {
            family = i;
            break;
        }
    }
    free(qprops);
    if (family == UINT32_MAX) { vkDestroyInstance(instance, NULL); fprintf(stderr, "VULKAN_FAIL no_queue\n"); return 2; }

    float priority = 1.0f;
    VkDeviceQueueCreateInfo qci = {0};
    qci.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    qci.queueFamilyIndex = family;
    qci.queueCount = 1;
    qci.pQueuePriorities = &priority;

    VkDeviceCreateInfo dci = {0};
    dci.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    dci.queueCreateInfoCount = 1;
    dci.pQueueCreateInfos = &qci;

    VkDevice device = VK_NULL_HANDLE;
    r = vkCreateDevice(pd, &dci, NULL, &device);
    if (r != VK_SUCCESS) { vkDestroyInstance(instance, NULL); return fail("vkCreateDevice", r); }

    VkQueue queue = VK_NULL_HANDLE;
    vkGetDeviceQueue(device, family, 0, &queue);

    VkFenceCreateInfo fci = {0};
    fci.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    VkFence fence = VK_NULL_HANDLE;
    r = vkCreateFence(device, &fci, NULL, &fence);
    if (r != VK_SUCCESS) { vkDestroyDevice(device, NULL); vkDestroyInstance(instance, NULL); return fail("vkCreateFence", r); }

    VkSubmitInfo submit = {0};
    submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    r = vkQueueSubmit(queue, 1, &submit, fence);
    if (r != VK_SUCCESS) {
        vkDestroyFence(device, fence, NULL);
        vkDestroyDevice(device, NULL);
        vkDestroyInstance(instance, NULL);
        return fail("vkQueueSubmit", r);
    }

    VkResult before = vkGetFenceStatus(device, fence);
    r = vkWaitForFences(device, 1, &fence, VK_TRUE, 5ULL * 1000ULL * 1000ULL * 1000ULL);
    if (r != VK_SUCCESS) {
        vkDestroyFence(device, fence, NULL);
        vkDestroyDevice(device, NULL);
        vkDestroyInstance(instance, NULL);
        return fail("vkWaitForFences", r);
    }
    VkResult after = vkGetFenceStatus(device, fence);
    if (after != VK_SUCCESS) {
        vkDestroyFence(device, fence, NULL);
        vkDestroyDevice(device, NULL);
        vkDestroyInstance(instance, NULL);
        return fail("vkGetFenceStatus(after)", after);
    }

    printf("VULKAN_PASS device=%s api=%u.%u.%u fence_before=%d fence_after=%d\n",
           props.deviceName,
           VK_VERSION_MAJOR(props.apiVersion), VK_VERSION_MINOR(props.apiVersion), VK_VERSION_PATCH(props.apiVersion),
           (int)before, (int)after);

    vkDestroyFence(device, fence, NULL);
    vkDestroyDevice(device, NULL);
    vkDestroyInstance(instance, NULL);
    return 0;
}
