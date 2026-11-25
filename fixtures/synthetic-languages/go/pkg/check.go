package pkg

func Check(value int) int {
    return helper(value)
}

func Recurse(value int) int {
    if value > 0 { return Recurse(value - 1) }
    return value
}

type Worker struct{}

func (w *Worker) Run(value int) int {
    return w.Finish(value)
}

func (w *Worker) Finish(value int) int {
    return Check(value)
}
