void main()
{
    texCoord_interp = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
