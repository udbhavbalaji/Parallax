package synthetic

import "example.test/synthetic/pkg"

func Run(value int) int {
    return pkg.Check(value)
}
