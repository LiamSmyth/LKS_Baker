const int MAX_EDGES = 512;

float edgeAlpha(vec2 p, vec2 pa, vec2 pb, float halfWidth, float aaSigma)
{
    vec2 ab = pb - pa;
    float abLenSq = max(dot(ab, ab), 1.0e-8);
    float t = clamp(dot(p - pa, ab) / abLenSq, 0.0, 1.0);
    vec2 closest = pa + t * ab;
    float dist = length(p - closest);
    if (dist <= halfWidth) {
        return 1.0;
    }
    float reach = halfWidth + aaSigma * 3.0;
    if (dist > reach) {
        return 0.0;
    }
    float edgeDist = dist - halfWidth;
    return exp(-(edgeDist * edgeDist) / (2.0 * aaSigma * aaSigma));
}

void main()
{
    vec4 params = texture(paramsTex, vec2(0.5)).rgba;
    float imageSize = params.r;
    float hw = params.g;
    float sigma = params.b;
    int edgeCount = int(params.a + 0.5);
    vec2 tc = texCoord_interp;
    vec2 p = vec2(tc.x * imageSize, (1.0 - tc.y) * imageSize);
    float strength = 0.0;
    for (int i = 0; i < MAX_EDGES; i++) {
        if (i >= edgeCount) {
            break;
        }
        vec4 edge = texture(edgeTex, vec2((float(i) + 0.5) / float(edgeCount), 0.5));
        strength = max(strength, edgeAlpha(p, edge.xy, edge.zw, hw, sigma));
    }
    fragColor = vec4(strength, 0.0, 0.0, 1.0);
}
