float islandAt(vec2 uv)
{
    return texture(islandTex, uv).r;
}

float maskAt(vec2 uv)
{
    return texture(maskTex, uv).r;
}

vec2 texelSize()
{
    ivec2 sz = textureSize(sourceTex, 0);
    return vec2(1.0) / vec2(float(sz.x), float(sz.y));
}

vec2 clampUv(vec2 uv)
{
    return clamp(uv, vec2(0.0), vec2(1.0));
}

float sampleMaskWeight(vec2 uv, float centerId)
{
    vec2 clamped = clampUv(uv);
    if (islandAt(clamped) != centerId) {
        return 0.0;
    }
    if (useBlurredWeight != 0) {
        return texture(weightTex, clamped).r;
    }
    if (maskAt(clamped) < 0.5) {
        return 0.0;
    }
    return 1.0;
}

float sampleField(vec2 uv, float centerId)
{
    vec2 clamped = clampUv(uv);
    if (islandAt(clamped) != centerId) {
        return 0.0;
    }
    if (useBlurredWeight == 0 && maskAt(clamped) < 0.5) {
        return 0.0;
    }
    return texture(sourceTex, clamped).r;
}

void main()
{
    vec2 uv = texCoord_interp;
    float centerId = islandAt(uv);
    if (centerId < 0.0) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    vec2 ts = texelSize();
    float valueSum = 0.0;
    float weightSum = 0.0;

    const int MAX_KERNEL = 256;
    for (int i = 0; i < MAX_KERNEL; i++) {
        if (i >= kernelSize) {
            break;
        }
        float kernelWeight = texture(kernelTex, vec2((float(i) + 0.5) / float(kernelSize), 0.5)).r;
        int offset = i - kernelRadius;
        vec2 delta = horizontalPass != 0
            ? vec2(float(-offset), 0.0) * ts
            : vec2(0.0, float(offset)) * ts;
        vec2 sampleUv = uv + delta;
        valueSum += kernelWeight * sampleField(sampleUv, centerId);
        weightSum += kernelWeight * sampleMaskWeight(sampleUv, centerId);
    }

    fragColor = vec4(valueSum, weightSum, 0.0, 1.0);
}
