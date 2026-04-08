extends Node
class_name MyClass

const Foo = preload("res://foo.gd")
const Bar = load("res://bar.gd")

signal hit(damage: int)

enum State { IDLE, RUN }

class Inner extends Resource:
    func helper() -> void:
        pass

func _ready() -> void:
    var x = Foo.new()
    helper()
    emit_signal("hit", 3)

static func util() -> int:
    return 1
