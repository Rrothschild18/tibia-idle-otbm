import Appearances_pb2

with open("Appearances.aec", "rb") as f:
    data = f.read()

appearances = Appearances_pb2.Appearances()
appearances.ParseFromString(data)

print("Appearances carregadas com sucesso")
print("Total de objetos:", len(appearances.object))
