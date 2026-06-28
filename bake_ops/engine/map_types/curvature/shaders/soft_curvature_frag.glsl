vec3 decodeNormal(vec2 uv) {
    return texture(normalTex, uv).rgb * 2.0 - 1.0;
}

vec3 readPosition(vec2 uv) {
    return texture(positionTex, uv).rgb;
}

float islandAt(vec2 uv) {
    return texture(islandTex, uv).r;
}

vec2 texelSize() {
    ivec2 sz = textureSize(positionTex, 0);
    return vec2(1.0) / vec2(float(sz.x), float(sz.y));
}

void main() {
    vec2 uv = texCoord_interp;
    float id = islandAt(uv);
    if (id < 0.0) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    vec3 pos = readPosition(uv);
    vec3 nrm = decodeNormal(uv);
    vec2 ts = texelSize();

    float kSum = 0.0;
    float kCount = 0.0;

    const int MAX_OFFSETS = 4096;
    for (int i = 0; i < MAX_OFFSETS; i++) {
        if (i >= numOffsets) {
            break;
        }
        vec2 offPx = texture(offsetsTex, vec2((float(i) + 0.5) / float(numOffsets), 0.5)).rg;
        int dx = int(round(offPx.r));
        int dy = int(round(offPx.g));
        if (dx == 0 && dy == 0) {
            continue;
        }
        /* flipud upload: PNG row +dy -> GL v +dy (see tangent_frag / internal_v_neighbor_indices). */
        vec2 uvN = uv + vec2(float(-dx), float(dy)) * ts;
        if (islandAt(uvN) != id) {
            continue;
        }
        vec3 nPos = readPosition(uvN);
        vec3 nNrm = decodeNormal(uvN);
        vec3 dP = nPos - pos;
        vec3 dN = nNrm - nrm;
        float dist2 = dot(dP, dP);
        if (dist2 <= 1e-20) {
            continue;
        }
        float k = -dot(dN, dP) / dist2;
        kSum += k;
        kCount += 1.0;
    }

    fragColor = vec4(kSum, kCount, 0.0, 1.0);
}
