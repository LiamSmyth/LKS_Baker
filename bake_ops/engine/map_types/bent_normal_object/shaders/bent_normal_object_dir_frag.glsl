vec3 decodeNormal(vec4 texel)
{
    return normalize(texel.rgb * 2.0 - 1.0);
}

vec2 texelSize()
{
    ivec2 sz = textureSize(positionTex, 0);
    return vec2(1.0) / vec2(float(sz.x), float(sz.y));
}

float islandAt(vec2 uv)
{
    return texture(islandTex, uv).r;
}

bool sameIsland(vec2 uv, vec2 other)
{
    float a = islandAt(uv);
    float b = islandAt(other);
    return a >= 0.0 && b >= 0.0 && abs(a - b) < 0.5;
}

vec3 positionAt(vec2 uv)
{
    return texture(positionTex, uv).rgb;
}

vec3 normalAt(vec2 uv)
{
    return decodeNormal(texture(normalTex, uv));
}

vec3 safeNormalize(vec3 v)
{
    float len = length(v);
    if (len < 1e-6) {
        return vec3(0.0, 0.0, 1.0);
    }
    return v / len;
}

void buildFrame(vec2 uv, out vec3 T, out vec3 B, out vec3 N)
{
    vec2 ts = texelSize();
    N = normalAt(uv);
    vec3 pL = positionAt(uv + vec2(-ts.x, 0.0));
    vec3 pR = positionAt(uv + vec2(ts.x, 0.0));
    vec3 pV = positionAt(uv + vec2(0.0, ts.y));
    vec3 pVm = positionAt(uv + vec2(0.0, -ts.y));
    T = safeNormalize(pR - pL);
    B = safeNormalize(cross(N, T));
    T = safeNormalize(cross(B, N));
}

bool directionOccluded(vec3 P, vec3 N, vec3 S, vec2 uv)
{
    vec2 ts = texelSize();
    float cosT = cos(uUvTheta);
    float sinT = sin(uUvTheta);
    int steps = int(uSteps);
    for (int step = 1; step <= 32; step++) {
        if (step > steps) {
            break;
        }
        float tFrac = float(step) / uSteps;
        float worldDist = uRadius * tFrac;
        int dx = int(round(cosT * worldDist / uDuMean));
        int dy = int(round(sinT * worldDist / uDvMean * uDySign));
        if (dx == 0 && dy == 0) {
            dx = cosT >= 0.0 ? 1 : -1;
        }
        vec2 offUv = uv + vec2(float(dx), float(dy)) * ts;
        if (!sameIsland(uv, offUv)) {
            continue;
        }
        vec3 Q = positionAt(offUv);
        vec3 vec = Q - P;
        float dist = length(vec);
        if (dist <= 1e-6 || dist > uRadius) {
            continue;
        }
        vec3 dirN = safeNormalize(vec);
        float align = dot(dirN, S);
        if (align > (1.0 - uBias)) {
            return true;
        }
    }
    return false;
}

void main()
{
    vec2 uv = texCoord_interp;
    float island = islandAt(uv);
    if (island < 0.0) {
        fragColor = vec4(0.0);
        return;
    }

    vec3 T;
    vec3 B;
    vec3 N;
    buildFrame(uv, T, B, N);
    vec3 S = safeNormalize(uLocalDir.x * T + uLocalDir.y * B + uLocalDir.z * N);
    if (dot(S, N) <= 1e-4) {
        fragColor = vec4(0.0);
        return;
    }

    vec3 P = positionAt(uv);
    if (directionOccluded(P, N, S, uv)) {
        fragColor = vec4(0.0);
        return;
    }

    fragColor = vec4(S, 1.0);
}
