package pkg

func helper(value int) int { return value + 1 }

func Unknown(value int, fn func(int) int) int { return fn(value) }

func shadow(helper func(int) int) int { return helper(1) }
