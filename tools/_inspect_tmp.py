import io, json
d=json.load(io.open('build/script.json',encoding='utf-8'))
ops=d['ops']
for i in range(0,40): print(i,ops[i])
